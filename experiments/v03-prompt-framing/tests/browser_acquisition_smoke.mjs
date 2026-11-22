// Offline end-to-end validation; isolated database and a fresh browser profile.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join,sep} from 'node:path';
import {createServer} from 'node:net';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..'), python=process.env.ECHOMIND_TEST_PYTHON||'C:\\Program Files\\Python311\\python.exe';
const scratch=await mkdtemp(join(tmpdir(),'echomind-prompt-framing-v03-ui-'));
const listener=createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;await new Promise(r=>listener.close(r));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,limit=45000){const start=Date.now();while(Date.now()-start<limit){try{const value=await fn();if(value)return value;}catch{}await pause(150);}throw Error('UI timeout');}
let backend,browser,ws;
try{
  backend=spawn(python,['-u',join(root,'server.py'),'--offline','--port',String(port)],{cwd:scratch,env:{...process.env,ECHOMIND_OFFLINE:'1',ECHOMIND_PILOT_DB:join(scratch,'isolated.sqlite3')},windowsHide:true,stdio:'ignore'});
  const url=`http://127.0.0.1:${port}`;await until(async()=>(await fetch(url+'/api/health')).ok);
  const profile=join(scratch,'edge');
  browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking','--disable-component-update','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugPort=await until(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]));
  const target=await until(async()=>(await(await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(t=>t.type==='page'));
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let serial=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
  function cdp(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
  const click=id=>evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);
  await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:url+'/#acquisition'});
  await until(()=>evaluate("document.querySelectorAll('#acq-scenarios input').length===4"));
  assert.equal(await evaluate("document.querySelector('#view-acquisition').hidden"),false);
  assert.equal(await evaluate("document.querySelector('#acq-repeats').value"),'3');
  assert.equal(await evaluate("document.querySelector('#acq-mode [value=live]').disabled"),true);
  assert.equal(await evaluate("document.querySelector('#acq-run').disabled"),true);
  await click('acq-preview');await until(()=>evaluate("!document.querySelector('#acq-run').disabled"));
  assert.equal(await evaluate("document.querySelector('#acq-example').options.length"),7);
  assert.ok(await evaluate("document.querySelector('#acq-count').textContent.includes('348')"));
  const before=await(await fetch(url+'/api/history/batches')).json();assert.equal(before.total_records,0);
  await evaluate("document.querySelector('#acq-repeats').value='2';document.querySelector('#acq-repeats').dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await evaluate("document.querySelector('#acq-run').disabled"),true);
  await evaluate("document.querySelector('#acq-repeats').value='3'");await click('acq-preview');await until(()=>evaluate("!document.querySelector('#acq-run').disabled"));
  await evaluate("document.querySelector('#acq-preview-details').open=false;window.scrollTo(0,0)");
  await writeFile(join(root,'data','acquisition-v02-setup.png'),Buffer.from((await cdp('Page.captureScreenshot',{format:'png'})).data,'base64'));
  await click('acq-run');await until(()=>evaluate("!!localStorage.getItem('echomind.prompt-framing-v03.job:'+location.origin)"));
  await evaluate("localStorage.removeItem('echomind.prompt-framing-v03.job:'+location.origin)");await cdp('Page.reload');
  try{await until(()=>evaluate("document.querySelector('#acq-result').textContent.includes('168 条已保存')"));}
  catch(error){console.error(await evaluate("document.querySelector('#acq-status').textContent"));throw error;}
  const batch=await evaluate("document.querySelector('#acq-batch').value"), suffix='?batch_id='+batch;
  const report=await(await fetch(url+'/api/acquisition/export.json'+suffix)).json();
  assert.equal(report.complete,168);assert.equal(report.snapshots.length,21);assert.equal(report.call_events.length,696);
  assert.equal(report.job.api_attempts,0);assert.equal(report.job.simulated_attempts,348);
  assert.equal(report.strata.length,1);assert.equal(report.strata[0].scenarios.length,4);
  assert.ok(report.strata[0].scenarios.every(s=>s.variants.length===2&&s.variants.every(v=>v.cells.length===7)));
  assert.equal(await evaluate("document.querySelector('#acq-snapshot').options.length"),21);
  assert.equal(await evaluate("document.querySelector('#acq-gate-review').hidden"),true);
  const csv=await(await fetch(url+'/api/acquisition/export.csv'+suffix)).text();
  assert.ok(csv.includes('row_type'));assert.ok(csv.includes('memory_snapshot'));assert.ok(csv.includes('call_event'));
  assert.deepEqual(await(await fetch(url+'/api/trials')).json(),[]);
  const history=await(await fetch(url+'/api/history/batch'+suffix)).json();assert.equal(history.acquisition_report.recorded,168);
  await evaluate("document.querySelector('#acq-result').scrollIntoView()");
  await writeFile(join(root,'data','acquisition-v02-results.png'),Buffer.from((await cdp('Page.captureScreenshot',{format:'png'})).data,'base64'));
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate('window.scrollTo(0,0)');await pause(200);
  assert.equal(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),true);
  await writeFile(join(root,'data','acquisition-v02-mobile.png'),Buffer.from((await cdp('Page.captureScreenshot',{format:'png'})).data,'base64'));
  await cdp('Page.reload');await until(()=>evaluate("document.querySelector('#acq-result').textContent.includes('168 条已保存')"));
  assert.deepEqual(errors,[]);
  await writeFile(join(root,'data','prompt-framing-v03-browser-result.json'),JSON.stringify({passed:true,mock_decisions:168,snapshots:21,simulated_requests:348,real_api_calls:0,paired_prompt_variants:['P0','P1'],refresh_recovery:true,independent_scenarios:4,desktop_mobile:true,formal_database_modified:false},null,2));
  console.log('PASS v0.3 UI: 168 MOCK decisions / 21 shared snapshots / 348 simulated requests; P0/P1 paired; preview invalidation; reload recovery; full audit exports; no JS errors; 0 real API calls.');
}finally{
  ws?.close();browser?.kill();backend?.kill();await pause(800);
  if(resolve(scratch).startsWith(resolve(tmpdir())+sep))await rm(scratch,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
}
