// Optional Windows UI acceptance: Node 22+ and installed Edge. Only MOCK is run.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join,sep} from 'node:path';
import {createServer} from 'node:net';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..');
const scratch=await mkdtemp(join(tmpdir(),'sos-state-ui-'));
const socket=createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));const port=socket.address().port;await new Promise(r=>socket.close(r));
let backend,browser,ws;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,limit=15000){const started=Date.now();while(Date.now()-started<limit){try{const value=await fn();if(value)return value}catch{}await pause(100)}throw Error('UI timeout')}
try{
  backend=spawn('python',['-u','server.py','--port',String(port)],{cwd:root,env:{...process.env,SOS_PILOT_DB:join(scratch,'ui.sqlite3')},windowsHide:true,stdio:'ignore'});
  const url=`http://127.0.0.1:${port}`;
  await until(async()=> (await fetch(url+'/api/state/bootstrap')).ok);
  const profile=join(scratch,'edge');
  browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-sandbox','--disable-background-networking','--disable-component-update','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugPort=await until(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]));
  const target=await until(async()=> (await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(t=>t.type==='page'));
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
  let serial=0;const pending=new Map(),exceptions=[];
  ws.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id){const item=pending.get(msg.id);pending.delete(msg.id);msg.error?item.reject(Error(JSON.stringify(msg.error))):item.resolve(msg.result)}else if(msg.method==='Runtime.exceptionThrown')exceptions.push(msg.params.exceptionDetails.text)};
  function cdp(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
  async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
  await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:url+'/study'});
  await until(()=>evaluate("document.querySelector('#connection')?.textContent==='本地服务已连接'"));
  assert.equal(await evaluate("document.querySelector('#provider').options.length"),5);
  assert.equal(await evaluate("document.querySelectorAll('.state-card').length"),3);
  await until(()=>evaluate("document.querySelector('#prompt').textContent.includes('[system]')"));
  assert.equal(await evaluate("/目标无焦虑|目标轻度|目标中度/.test(document.querySelector('#prompt').textContent)"),false);
  await evaluate("document.querySelector('#mode').value='mock';document.querySelector('#run').click()");
  await until(()=>evaluate("document.querySelector('#progress').textContent.includes('已结束')"));
  assert.equal(await evaluate("document.querySelectorAll('.metric').length"),3);
  assert.equal(await evaluate("document.querySelectorAll('.response .text').length"),3);
  const report=await (await fetch(url+'/api/state/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:'MOCK_NOT_LLM'})})).json();
  assert.equal(report.n,3);assert.equal(report.groups[0].human_matches.length,0);
  const original=await evaluate("document.querySelector('#memoryEditors textarea').value");
  const amended=original.replace('\n','那天是下午。\n');
  await evaluate(`document.querySelector('#memoryEditors textarea').value=${JSON.stringify(amended)};document.querySelector('#saveMaterials').click()`);
  await until(()=>evaluate("document.querySelector('#toast').textContent.includes('已保存')"));
  await cdp('Page.reload');await until(()=>evaluate("document.querySelector('#memoryEditors textarea')?.value"));
  assert.equal(await evaluate("document.querySelector('#memoryEditors textarea').value"),amended);
  await evaluate("document.querySelector('#controls').checked=true;document.querySelector('#variant').value='all';document.querySelector('#scope').value='development';document.querySelector('#scope').dispatchEvent(new Event('change'))");
  await until(()=>evaluate("document.querySelector('#estimate').textContent.includes('45 个模拟试次')"));
  assert.deepEqual(exceptions,[]);
  await evaluate('window.scrollTo(0,0)');
  const screenshot=await cdp('Page.captureScreenshot',{format:'png'});
  await writeFile(join(root,'data','state-demo-test.png'),Buffer.from(screenshot.data,'base64'));
  console.log('PASS: five providers, three state cards, prompt isolation, MOCK run, three result cards, save/reload, 45-trial estimate, no browser exceptions.');
}finally{
  ws?.close();browser?.kill();backend?.kill();await pause(800);
  if(resolve(scratch).startsWith(resolve(tmpdir())+sep))await rm(scratch,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
}
