// Isolated browser acceptance. Only MOCK requests, temporary SQLite and Edge profile.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join,sep} from 'node:path';
import {createServer} from 'node:net';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..');
const scratch=await mkdtemp(join(tmpdir(),'sos-mechanism-ui-'));
const socket=createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));
const port=socket.address().port;await new Promise(r=>socket.close(r));
let backend,browser,ws;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,limit=20000) {
  const started=Date.now();
  while(Date.now()-started<limit){try{const value=await fn();if(value)return value;}catch{}await pause(100);}
  throw Error('UI timeout');
}
try {
  backend=spawn('python',['-u','server.py','--port',String(port)],{
    cwd:root,env:{...process.env,SOS_PILOT_DB:join(scratch,'ui.sqlite3')},windowsHide:true,stdio:'ignore'
  });
  const url=`http://127.0.0.1:${port}`;
  await until(async()=> (await fetch(url+'/api/mechanism/bootstrap')).ok);
  const profile=join(scratch,'edge');
  browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
    '--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking',
    '--disable-component-update','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'
  ],{windowsHide:true,stdio:'ignore'});
  const debugPort=await until(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]));
  const target=await until(async()=> (await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(t=>t.type==='page'));
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let serial=0;const pending=new Map(),exceptions=[];
  ws.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.id){const item=pending.get(msg.id);pending.delete(msg.id);msg.error?item.reject(Error(JSON.stringify(msg.error))):item.resolve(msg.result);}
    else if(msg.method==='Runtime.exceptionThrown') exceptions.push(msg.params.exceptionDetails.text);
  };
  function cdp(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){
    const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(r.exceptionDetails)throw Error(r.exceptionDetails.text);
    return r.result.value;
  }
  await cdp('Runtime.enable');await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url});
  await until(()=>evaluate("document.querySelector('#connection')?.textContent==='本地服务已连接'"));
  await until(()=>evaluate("!document.querySelector('#run').disabled"));
  assert.equal(await evaluate("document.querySelector('#repeats').value"),'20');
  assert.equal(await evaluate("document.querySelectorAll('.condition').length"),3);
  await until(()=>evaluate("document.querySelector('#prompt').textContent.includes('内心想法')"));
  assert.equal(await evaluate("/目标无焦虑|目标轻度|目标中度|state_none/.test(document.querySelector('#prompt').textContent)"),false);
  assert.match(await evaluate("document.querySelector('#estimate').textContent"),/60 个 MOCK/);
  await evaluate("document.querySelector('#run').click()");
  await until(()=>evaluate("document.querySelector('#progress').textContent.includes('已结束')"));
  await until(()=>evaluate("document.querySelectorAll('.metric').length===3"));
  assert.equal(await evaluate("document.querySelectorAll('.response .channel').length"),9);
  assert.match(await evaluate("document.querySelector('#verdict').textContent"),/尚无模型证据/);
  const batch=await evaluate("document.querySelector('#batch').value");
  const report=await (await fetch(url+'/api/mechanism/report',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({batch_id:batch})
  })).json();
  assert.equal(report.complete_n,60);
  assert.equal(report.verdict.status,'mock');
  assert.ok(report.records.every(r=>r.output_format==='public-channels-v1'));
  const missing=report.records.find(r=>!r.channels.behavior);
  assert.ok(missing);
  await evaluate(`document.querySelector('#sample').value='${missing.repeat}';document.querySelector('#sample').dispatchEvent(new Event('change'))`);
  assert.match(await evaluate("document.querySelector('#responses').textContent"),/未提供/);
  const exported=await (await fetch(url+`/api/mechanism/export.json?batch_id=${batch}`)).json();
  assert.equal(exported.records.length,60);
  const csv=await (await fetch(url+`/api/mechanism/export.csv?batch_id=${batch}`)).text();
  assert.match(csv.split('\n')[0],/thought,speech,behavior/);
  await cdp('Page.reload');
  await until(()=>evaluate("document.querySelectorAll('.metric').length===3"));
  assert.equal(await evaluate("document.querySelector('#batch').value"),batch);
  assert.equal(await evaluate("document.querySelector('#sample').options.length"),20);
  await evaluate("document.querySelector('#repeats').value='101';document.querySelector('#repeats').dispatchEvent(new Event('change'))");
  await until(()=>evaluate("document.querySelector('#estimate').textContent.includes('1–100')"));
  assert.equal(await evaluate("document.querySelector('#run').disabled"),true);
  await evaluate("document.querySelector('#repeats').value='20';document.querySelector('#repeats').dispatchEvent(new Event('change'))");
  await until(()=>evaluate("!document.querySelector('#run').disabled"));
  await evaluate("window.scrollTo(0,0)");
  let screenshot=await cdp('Page.captureScreenshot',{format:'png'});
  await writeFile(join(root,'data','demo-mechanism-desktop.png'),Buffer.from(screenshot.data,'base64'));
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await pause(300);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  screenshot=await cdp('Page.captureScreenshot',{format:'png'});
  await writeFile(join(root,'data','demo-mechanism-mobile.png'),Buffer.from(screenshot.data,'base64'));
  assert.deepEqual(exceptions,[]);
  console.log('PASS: 60 MOCK trials, three channels, optional omissions, fixed prompts, ratios, source gate, per-batch exports, reload, invalid count, desktop/mobile layout, no JS exceptions.');
} finally {
  ws?.close();browser?.kill();backend?.kill();await pause(800);
  if(resolve(scratch).startsWith(resolve(tmpdir())+sep)) await rm(scratch,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
}
