// New protocol end to end, isolated SQLite and fresh Edge profile, offline only.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join,sep} from 'node:path';
import {createServer} from 'node:net';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..');
const python=process.env.ECHOMIND_TEST_PYTHON||'C:\\Program Files\\Python311\\python.exe';
const scratch=await mkdtemp(join(tmpdir(),'echomind-source-v2-ui-'));
const listener=createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;await new Promise(r=>listener.close(r));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,limit=30000){const began=Date.now();while(Date.now()-began<limit){try{const x=await fn();if(x)return x;}catch{}await pause(100);}throw Error('UI timeout');}
let backend,browser,ws;
try {
  backend=spawn(python,['-u',join(root,'server.py'),'--offline','--port',String(port)],{cwd:scratch,env:{...process.env,ECHOMIND_OFFLINE:'1',ECHOMIND_PILOT_DB:join(scratch,'isolated.sqlite3')},windowsHide:true,stdio:'ignore'});
  const url=`http://127.0.0.1:${port}`;await until(async()=>(await fetch(url+'/api/health')).ok);
  const profile=join(scratch,'edge');
  browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking','--disable-component-update','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugPort=await until(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]));
  const target=await until(async()=>(await(await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(t=>t.type==='page'));
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let serial=0;const pending=new Map(),exceptions=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails.text);};
  function cdp(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
  const click=id=>evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);
  await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:url+'/#measurement'});
  await until(()=>evaluate("document.querySelectorAll('#m-versions input').length===2"));
  assert.equal(await evaluate("document.querySelector('#view-measurement').hidden"),false);
  assert.equal(await evaluate("document.querySelector('#m-mode [value=live]').disabled"),true);
  assert.equal(await evaluate("document.querySelector('#m-run').disabled"),true);
  await click('m-preview');await until(()=>evaluate("!document.querySelector('#m-run').disabled"));
  assert.equal(await evaluate("document.querySelector('#m-example').options.length"),8);
  assert.ok(await evaluate("document.querySelector('#m-prompt').textContent.includes('经历主体')"));
  await evaluate("document.querySelector('#m-repeats').value='2';document.querySelector('#m-repeats').dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await evaluate("document.querySelector('#m-run').disabled"),true);
  await click('m-quick');await click('m-preview');await until(()=>evaluate("!document.querySelector('#m-run').disabled"));
  const empty=await(await fetch(url+'/api/history/batches')).json();assert.equal(empty.total_records,0);
  await click('m-run');await until(()=>evaluate("document.querySelector('#m-result').textContent.includes('8 条已保存')"));
  assert.ok(await evaluate("document.querySelector('#m-result').textContent.includes('不是研究证据')"));
  const batch=await evaluate("document.querySelector('#m-batch').value");
  let report=await(await fetch(url+'/api/measurement/report?batch_id='+batch)).json();
  assert.equal(report.recorded,8);assert.ok(report.strata.every(x=>x.source_interaction===0));
  await cdp('Page.reload');await until(()=>evaluate("document.querySelector('#m-result').textContent.includes('8 条已保存')"));
  await click('m-pilot');await click('m-preview');await until(()=>evaluate("!document.querySelector('#m-run').disabled"));
  assert.equal(await evaluate("document.querySelector('#m-example').options.length"),64);
  assert.ok(await evaluate("document.querySelector('#m-count').textContent.includes('192')"));
  await evaluate("document.querySelector('#m-preview-details').open=false;window.scrollTo(0,0)");
  const setup=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(root,'data','source-v2-setup.png'),Buffer.from(setup.data,'base64'));
  await click('m-run');
  // Reload an accepted job, rather than cancelling a POST before it was sent.
  await until(()=>evaluate("!!localStorage.getItem('echomind.source-v2.job:'+location.origin)"));
  await evaluate("localStorage.removeItem('echomind.source-v2.job:'+location.origin)");
  await cdp('Page.reload');
  try { await until(()=>evaluate("document.querySelector('#m-result').textContent.includes('192 条已保存')")); }
  catch(error){console.error(await evaluate("({status:document.querySelector('#m-status')?.textContent,batch:document.querySelector('#m-batch')?.value,result:document.querySelector('#m-result')?.textContent.slice(0,300)})"));throw error;}
  const fullBatch=await evaluate("document.querySelector('#m-batch').value");
  report=await(await fetch(url+'/api/measurement/export.json?batch_id='+fullBatch)).json();
  assert.equal(report.recorded,192);assert.equal(report.strata.length,16);assert.ok(report.strata.every(x=>x.source_interaction===0));
  assert.ok(report.strata.every(s=>s.cells.every(c=>c.both_present===1&&c.negative_present===2)));
  const blind=await(await fetch(url+'/api/review/export.csv?batch_id='+fullBatch)).text();
  assert.ok(blind.includes('negative_evidence'));assert.ok(!blind.includes('self_adverse'));
  await evaluate("document.querySelector('#m-result').scrollIntoView()");
  const result=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(root,'data','source-v2-results.png'),Buffer.from(result.data,'base64'));
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(200);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  const mobile=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(root,'data','source-v2-mobile.png'),Buffer.from(mobile.data,'base64'));
  await click('tab-history');await click('hist-refresh');
  await until(()=>evaluate("document.querySelectorAll('#hist-batches tbody tr').length===2"));
  await until(()=>evaluate("document.querySelector('#hist-detail').textContent.includes('独立多维编码')"));
  assert.ok(await evaluate("document.querySelector('#hist-detail').textContent.includes('空白归因盲评表')"));
  const final=await(await fetch(url+'/api/history/batches')).json();assert.equal(final.total_records,200);
  assert.deepEqual(exceptions,[]);
  await writeFile(join(root,'data','source-v2-browser-result.json'),JSON.stringify({passed:true,external_api_calls:0,mock_records_in_temporary_database:200,pilot_cells:64,pilot_strata:16,all_mock_interactions_zero:true,main_database_modified:false},null,2));
  console.log('PASS source-v2: 8 + 192 MOCK records in temporary database; preview invalidation; 64 prompts; refresh during run; history/export/blank review; 16 strata D=0; desktop/mobile; no JS errors; no real API calls.');
} finally {
  ws?.close();browser?.kill();backend?.kill();await pause(800);
  if(resolve(scratch).startsWith(resolve(tmpdir())+sep))await rm(scratch,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
}
