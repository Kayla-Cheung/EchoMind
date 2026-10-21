// Real historical data, read-only SQLite backup into an isolated temporary workspace.
// All mutations below affect that copy. No credentials and no live API requests.
import {spawn,spawnSync} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join,sep} from 'node:path';
import {createServer} from 'node:net';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..'), python=process.env.SOS_TEST_PYTHON||'C:\\Program Files\\Python311\\python.exe';
const scratch=await mkdtemp(join(tmpdir(),'sos-research-ui-'));
const listener=createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;await new Promise(r=>listener.close(r));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,limit=25000){const began=Date.now();while(Date.now()-began<limit){try{const v=await fn();if(v)return v;}catch{}await pause(100);}throw Error('UI timeout');}
let backend,browser,ws;
try {
  const database=join(scratch,'copy.sqlite3');
  const copied=spawnSync(python,['-c','import sqlite3,sys; from pathlib import Path; s=sqlite3.connect(Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()',join(root,'data','pilot.sqlite3'),database],{windowsHide:true,encoding:'utf8'});
  assert.equal(copied.status,0,copied.stderr);
  backend=spawn(python,['-u',join(root,'server.py'),'--offline','--port',String(port)],{cwd:scratch,env:{...process.env,SOS_OFFLINE:'1',SOS_PILOT_DB:database},windowsHide:true,stdio:'ignore'});
  const url=`http://127.0.0.1:${port}`;await until(async()=>(await fetch(url+'/api/health')).ok);
  const initial=await(await fetch(url+'/api/history/batches')).json();
  assert.ok(initial.total_records>=362);assert.ok(initial.batches.length>=14);
  const profile=join(scratch,'edge');
  browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking','--disable-component-update','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugPort=await until(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]));
  const target=await until(async()=>(await(await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(t=>t.type==='page'));
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let serial=0;const pending=new Map(),exceptions=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails.text);};
  function cdp(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
  await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url});
  await until(()=>evaluate(`document.querySelector('#hist-overview')?.textContent.includes('${initial.total_records}')`));
  assert.equal(await evaluate("document.querySelectorAll('#hist-batches tbody tr').length"),initial.batches.length);
  assert.equal(await evaluate("document.querySelector('#view-history').hidden"),false);
  const A='820cb1f4-daf7-43be-a671-d4a62c43491a',B='46c4575c-86d3-4f9a-99fb-1d97bcfffcc3';
  await evaluate(`document.querySelector('#hist-selected').value='${A}';document.querySelector('#hist-selected').dispatchEvent(new Event('change'))`);
  await until(()=>evaluate("document.querySelectorAll('#hist-detail .hist-record').length===60"));
  assert.ok(await evaluate("document.querySelector('#hist-detail').textContent.includes('19/20')"));
  assert.ok(await evaluate("document.querySelector('#hist-detail').textContent.includes('role_messages')"));
  await evaluate(`document.querySelector('#hist-compare').value='${B}';document.querySelector('#hist-compare').dispatchEvent(new Event('change'))`);
  await until(()=>evaluate("document.querySelectorAll('#hist-comparison .hist-record').length===24"));
  await evaluate("document.querySelector('#hist-status').value='error';document.querySelector('#hist-status').dispatchEvent(new Event('change'))");
  assert.equal(await evaluate("document.querySelectorAll('#hist-batches tbody tr').length"),initial.batches.filter(b=>b.error>0).length);
  await evaluate("document.querySelector('#hist-status').value='';document.querySelector('#hist-protocol').value='memory-ablation-v1';document.querySelector('#hist-source').value='LIVE_LLM_API';document.querySelector('#hist-source').dispatchEvent(new Event('change'))");
  assert.equal(await evaluate("document.querySelectorAll('#hist-batches tbody tr').length"),4);
  const exported=await(await fetch(url+'/api/history/export.json?batch_id='+A)).text();
  const importFile=join(scratch,'duplicate.json');await writeFile(importFile,exported);
  const dom=await cdp('DOM.getDocument');const input=await cdp('DOM.querySelector',{nodeId:dom.root.nodeId,selector:'#hist-file'});
  await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[importFile]});
  await evaluate("document.querySelector('#hist-preview').click()");
  await until(()=>evaluate("!document.querySelector('#hist-commit').disabled"));
  assert.equal(await evaluate("JSON.parse(document.querySelector('#hist-import-result').textContent).duplicate_n"),60);
  await evaluate("document.querySelector('#hist-commit').click()");
  await until(()=>evaluate("document.querySelector('#hist-commit').disabled && JSON.parse(document.querySelector('#hist-import-result').textContent).imported===0"));
  await evaluate("document.querySelector('#tab-prompts').click()");
  await until(()=>evaluate("document.querySelector('#prompt-version').options.length===2"));
  await evaluate("document.querySelector('#prompt-preview').click()");
  await until(()=>evaluate("document.querySelector('#prompt-rendered').textContent.includes('offline_template_preview')"));
  await evaluate("const box=document.querySelector('#prompt-editor');const p=JSON.parse(box.value);p.version='ui-test-v2.1';box.value=JSON.stringify(p);document.querySelector('#prompt-save').click()");
  await until(()=>evaluate("document.querySelector('#prompt-version').value==='ui-test-v2.1'"));
  await cdp('Page.reload');await until(()=>evaluate("document.querySelector('#prompt-version').options.length===3"));
  await evaluate("document.querySelector('#tab-history').click()");
  await until(()=>evaluate(`document.querySelectorAll('#hist-batches tbody tr').length===${initial.batches.length}`));
  const shot=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(root,'data','research-history-desktop.png'),Buffer.from(shot.data,'base64'));
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(300);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  const mobile=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(root,'data','research-history-mobile.png'),Buffer.from(mobile.data,'base64'));
  assert.deepEqual(exceptions,[]);
  console.log(`PASS: ${initial.total_records} historical records / ${initial.batches.length} batches; A 60 + B 24; failure/protocol filters; prompt/raw drilldown; duplicate import; version save/reload; desktop/mobile; no JS exceptions; no live API calls.`);
} finally {
  ws?.close();browser?.kill();backend?.kill();await pause(800);
  if(resolve(scratch).startsWith(resolve(tmpdir())+sep))await rm(scratch,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
}
