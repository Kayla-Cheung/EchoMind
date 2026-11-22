'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={none:'无记忆',neutral_direct:'中性记忆',negative_direct:'负面记忆'};
async function get(url){const r=await fetch(url);const body=await r.json();if(!r.ok)throw new Error(body.error||'无法读取本地数据');return body}
document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('nav button,.view').forEach(x=>x.classList.remove('active'));button.classList.add('active');$('#'+button.dataset.view).classList.add('active')}));
let previewSequence=0;
async function preview(){const sequence=++previewSequence;const arm=$('#arm').value;$('#scenario').disabled=arm==='BATCH';const query=new URLSearchParams({arm,condition:$('#condition').value,scenario:$('#scenario').value});try{const p=await get('/api/preview?'+query);if(sequence!==previewSequence)return;$('#preview-facts').innerHTML=[`${p.scenarios} 个情境`,`${p.memory_messages} 份记忆（本对话中一次）`,`${p.rating_items} 个评分选项`,'预览 · 0 次模型调用'].map(x=>`<span>${esc(x)}</span>`).join('');for(const phase of ['encoding','rating']){$('#'+phase).innerHTML=p[phase].map((m,i)=>`<details class="message" ${i===p[phase].length-1?'open':''}><summary>${i+1} · ${esc(m.role.toUpperCase())}</summary><pre>${esc(m.content)}</pre></details>`).join('')}}catch(e){$('#preview-facts').textContent=e.message}}
for(const id of ['arm','condition','scenario'])$('#'+id).addEventListener('change',preview);
async function load(){try{const s=await get('/api/status'),r=s.report,j=s.journal;$('#loading').hidden=true;$('#content').hidden=false;$('#episode-count').textContent=j.complete;$('#request-count').textContent=j.valid_requests;$('#rating-count').textContent=j.counts.ratings;$('#new-calls').textContent=j.counts.requests;$('#episode-progress').style.width=`${j.complete/60*100}%`;$('#blockers').innerHTML=r.blockers.map((b,i)=>`<article class="blocker"><span class="number">0${i+1}</span><div><h3>${esc(b.title)}</h3><p>${esc(b.detail)}</p></div></article>`).join('');$('#checks').innerHTML=r.checks.map(c=>`<div class="check"><span>${esc(c.label)}</span><b class="${['NO-GO','UNRECONCILED'].includes(c.state)?'blocked':''}">${esc(c.state)}</b></div>`).join('');$('#limitations').innerHTML=r.limitations.map(x=>`<li>${esc(x)}</li>`).join('');$('#scenario').innerHTML=s.scenarios.map(x=>`<option value="${esc(x.id)}">${esc(x.id)} · ${esc(x.title)}</option>`).join('');
const columns=['all',...s.scenarios.map(x=>x.id)];let table='<div class="matrix-wrap"><table class="matrix"><thead><tr><th>记忆 × 呈现</th>'+columns.map(x=>`<th>${x==='all'?'Batch · 全部':esc(x)}</th>`).join('')+'</tr></thead><tbody>';for(const condition of Object.keys(labels)){for(const arm of ['BATCH','ISOLATED']){table+=`<tr><th>${labels[condition]}<br>${arm}</th>`+columns.map(scenario=>{const cells=j.episodes.filter(e=>e.arm===arm&&e.condition_id===condition&&e.scenario_id===scenario).sort((a,b)=>a.repeat_index-b.repeat_index);return '<td>'+cells.map(e=>`<span class="cell ${e.status==='complete'?'complete':''}" title="重复 ${e.repeat_index} · ${esc(e.status==='planned'?'未开始':e.status)}"></span>`).join('')+'</td>'}).join('')+'</tr>'}}$('#matrix').innerHTML=table+'</tbody></table></div><p class="matrix-legend">每个小方格是一个独立对话。浅色：未开始；绿色：已完成。当前仅创建计划，没有真实结果。</p>';
const h=r.history;$('#history-cards').innerHTML=[['原始 v0.5',`${h.v05_requests} 次请求 · ${h.v05_ratings} 评分`,'$'+h.v05_peak_conservative_usd,'峰值价格保守记账，含失败请求'],['Prompt-Valence',`${h.valence_requests} 次请求 · ${h.valence_ratings} 评分`,'$'+h.valence_offpeak_usage_usd,'非高峰用量推算；不属于本次 Isolated 结果'],['更早的 EchoMind',`${h.legacy_distinct_deepseek_responses} 个去重的 DeepSeek 响应`,'$'+h.legacy_deduplicated_recorded_job_cost_usd,'已记账作业费用小计；累计授权范围待核清']].map(x=>`<article class="history-card"><h3>${esc(x[0])}</h3><b>${esc(x[2])}</b><p>${esc(x[1])}</p><p>${esc(x[3])}</p></article>`).join('');$('#cost-bound').textContent='$'+Number(r.cost.offpeak_diagnostic_usd).toFixed(7)+' USD';$('#billing-caveat').textContent=h.billing_caveat+' 原始 v0.5 与 Prompt-Valence 的混合保守小计为 $'+h.v05_plus_valence_mixed_conservative_usd+'；这不是已核清的全项目余额。';$('#observed').textContent='核对时间 '+new Date(r.observed_utc).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+'（上海）';await preview()}catch(e){$('#loading').textContent='工作台未能读取记录：'+e.message;$('#loading').classList.add('load-error')}}
load();

// Update live progress independently, preserving the user's selected preview controls.
let renderedResults=false;
async function refreshRuntime(){try{
 const s=await get('/api/status'),r=s.report,j=s.journal;
 const done=j.complete===60&&j.valid_requests===120&&j.counts.ratings===432;
 const authorized=r.decision==='GO';
 $('#episode-count').textContent=j.complete;$('#request-count').textContent=j.valid_requests;
 $('#rating-count').textContent=j.counts.ratings;$('#new-calls').textContent=j.counts.requests;
 $('#episode-progress').style.width=`${j.complete/60*100}%`;
 if(authorized){
  $('.gate-banner').classList.add('go');$('.status-label').textContent=done?'COMPLETE · REAL':j.counts.requests?'RUNNING · REAL':'READY · REAL';
  $('.gate-banner strong').textContent=done?'完整真实对照已完成':j.counts.requests?'预检通过，完整真实对照正在运行':'预检通过，等待真实运行';
  $('.gate-banner p').textContent=r.actual_usage_derived_cost_usd?`本轮费用（按用量核算）$${r.actual_usage_derived_cost_usd}，独立上限 $0.13；历史旧账另行核对。`:'本轮已单独授权新增费用上限 $0.13；历史累计费用仍另行核对，不自动重试。';
  const budget=document.querySelector('.metrics article:last-child');budget.querySelector('strong').innerHTML='$0.13<small> USD</small>';
  budget.querySelector('p').textContent='本轮独立预算 · 旧账另行核对';
  document.querySelector('.budget-detail span:first-child b').textContent='$0.130000';
  if(!r.blockers.length)$('#blockers').innerHTML='<article class="blocker"><span class="number">GO</span><div><h3>本轮独立预算与发送前检查已通过</h3><p>固定 DeepSeek 模型、原 P0 与 60 个对话设计；每阶段只尝试一次，发生异常即停止。</p></div></article>';
  $('#overview .note p:last-child').textContent=done?'本次已形成完整平衡矩阵，可在“真实结果”页查看描述性 W1。每题每条件每组仅 2 个模型样本。':'完整矩阵形成后才显示 W1，不用历史评分代替本次结果。';
 }
 const progress=document.querySelector('#design .section-head p');progress.textContent=`两次重复 × 三种记忆。每个标记对应一个独立对话：已完成 ${j.complete}／60。`;
 const legend=document.querySelector('.matrix-legend');if(legend)legend.textContent=`每个方格代表独立对话。浅色：未开始或进行中；绿色：完成。当前已完成 ${j.complete}／60。`;
 let allMarkers=[];for(const condition of Object.keys(labels))for(const arm of ['BATCH','ISOLATED'])for(const scenario of ['all',...s.scenarios.map(x=>x.id)])allMarkers.push(...j.episodes.filter(e=>e.arm===arm&&e.condition_id===condition&&e.scenario_id===scenario).sort((a,b)=>a.repeat_index-b.repeat_index));
 document.querySelectorAll('.cell').forEach((el,i)=>{if(allMarkers[i]){el.classList.toggle('complete',allMarkers[i].status==='complete');el.title=`重复 ${allMarkers[i].repeat_index} · ${allMarkers[i].status}`}});
 if(done&&!renderedResults){
  const result=await get('/api/results');if(result.status!=='complete')return;
  const a=result.analysis;let html='<div class="notice">本次是真实模型数据。每题／记忆／组 n=2，仅作可行性和描述性比较；不能据此认定稳定拟合或心理机制。</div>';
  for(const group of ['all36','social12']){html+=`<h3>${group==='all36'?'全部 36 题':'社交情境 12 题'} · 配对题目平均 W1</h3><div class="matrix-wrap"><table class="matrix result-table"><thead><tr><th>记忆</th><th>Batch</th><th>Isolated</th><th>Isolated − Batch</th></tr></thead><tbody>`;
   for(const x of a.summaries.filter(x=>x.group===group))html+=`<tr><th>${labels[x.condition]}</th><td>${x.BATCH.toFixed(4)}</td><td>${x.ISOLATED.toFixed(4)}</td><td>${x.isolated_minus_batch.toFixed(4)}</td></tr>`;
   html+='</tbody></table></div>';
  }
  html+='<p class="sources">负差表示本次 Isolated 的距离较低；不同记忆条件均比较到未注入记忆的人类 preTest 参考。</p><h3>评分频数 · 每组 216 条</h3><div class="matrix-wrap"><table class="matrix result-table"><thead><tr><th>组别</th><th>1 分</th><th>2 分</th><th>3 分</th><th>4 分</th></tr></thead><tbody>';
  for(const arm of ['BATCH','ISOLATED'])html+=`<tr><th>${arm}</th>${[1,2,3,4].map(score=>`<td>${Object.values(a.frequency[arm]).reduce((sum,c)=>sum+c[String(score)],0)}</td>`).join('')}</tr>`;
  html+='</tbody></table></div><details class="message"><summary>查看各情境 W1（每情境 4 题）</summary><div class="matrix-wrap"><table class="matrix result-table"><thead><tr><th>记忆／情境</th><th>Batch</th><th>Isolated</th><th>差值</th></tr></thead><tbody>';
  for(const x of a.summaries.filter(x=>!['all36','social12'].includes(x.group)))html+=`<tr><th>${labels[x.condition]}／${esc(x.group)}</th><td>${x.BATCH.toFixed(4)}</td><td>${x.ISOLATED.toFixed(4)}</td><td>${x.isolated_minus_batch.toFixed(4)}</td></tr>`;
  html+='</tbody></table></div></details><a class="download" href="/api/results" download="RR-ISOLATION-001-analysis.json">下载完整题目配对分析 JSON</a> <a class="download" href="/api/export/ratings.csv" download="RR-ISOLATION-001-ratings.private.csv">下载 432 条模型评分（私有）</a>';
  $('#real-result-content').innerHTML=html;renderedResults=true;
 }
}catch(e){/* Preserve the latest successfully read evidence during a transient refresh. */}}
refreshRuntime();setInterval(refreshRuntime,3000);


