(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  const pretty = value => JSON.stringify(value, null, 2);
  const option = (value, label) => `<option value="${esc(value)}">${esc(label)}</option>`;
  async function api(path, data) {
    const res = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const value = await res.json(); if (!res.ok) throw new Error(value.error || res.status); return value;
  }
  const error = (id, ex) => { $(id).textContent = ex.message; };
  let all = [], preview = null, importedDocument = null, versions = [], generation = 0;
  function filters() { const q = new URLSearchParams(); for (const key of ['from','to','model','protocol','source','status']) if ($('hist-' + key).value) q.set(key, $('hist-' + key).value); return q; }
  function filtered() {
    const f = Object.fromEntries(filters());
    return all.filter(b => (!f.from || b.date >= f.from) && (!f.to || b.date <= f.to) &&
      ['model','protocol','source'].every(k => !f[k] || b[k+'s'].includes(f[k])) && (!f.status || b.statuses[f.status]));
  }
  function renderList() {
    const rows = filtered(), old = $('hist-selected').value, compare = $('hist-compare').value;
    $('hist-batches').innerHTML = '<table><thead><tr><th>日期 / 批次</th><th>模型 / 协议 / 来源</th><th>成功</th><th>失败</th><th>总记录</th></tr></thead><tbody>' + rows.map(b => `<tr><td><button data-batch="${esc(b.id)}">${esc(b.id.slice(0,8))}</button><br>${esc(b.date)}</td><td>${esc(b.models.join(', '))}<br>${esc(b.protocols.join(', '))}<br><span class="hist-tag">${esc(b.sources.join(', '))}</span></td><td>${b.complete}</td><td>${b.error}</td><td>${b.n}</td></tr>`).join('') + '</tbody></table>';
    const opts = rows.map(b => option(b.id, `${b.date} · ${b.id.slice(0,8)} · ${b.models.join('/')} · ${b.protocols.join('/')} · ${b.complete}/${b.n}`)).join('');
    $('hist-selected').innerHTML = opts; $('hist-compare').innerHTML = option('', '不对照') + opts;
    if (rows.some(x => x.id === old)) $('hist-selected').value = old;
    if (rows.some(x => x.id === compare)) $('hist-compare').value = compare;
    const query = filters().toString();
    $('hist-export-json').href = '/api/history/export.json?' + query;
    $('hist-export-csv').href = '/api/history/export.csv?' + query;
    renderDetails();
  }
  async function refresh() {
    try {
      const [result, health] = await Promise.all([api('/api/history/batches'), api('/api/health')]);
      all = result.batches;
      $('hist-overview').textContent = `${all.length} 个批次 · ${result.total_records} 条原始记录 · ${all.reduce((n,b)=>n+b.complete,0)} 条成功（含 MOCK） · ${all.reduce((n,b)=>n+b.error,0)} 条失败`;
      $('hist-database').textContent = '持久化数据库：' + result.database;
      $('workspace-connection').textContent = health.offline ? '离线审计模式 · 仅可运行 MOCK' : '本地服务已连接';
      if (health.offline) for (const id of ['mode','abl-mode']) { const control=$(id); if(control) {control.value='mock'; const live=control.querySelector('option[value="live"]'); if(live) live.disabled=true;} }
      for (const key of ['model','protocol']) {
        const previous=$('hist-'+key).value;
        $('hist-'+key).innerHTML=option('', '全部') + [...new Set(all.flatMap(b=>b[key+'s']))].sort().map(v=>option(v,v)).join('');
        if ([...$('hist-'+key).options].some(o=>o.value===previous)) $('hist-'+key).value=previous;
      }
      renderList();
    } catch (ex) { error('hist-overview',ex); }
  }
  function detailHTML(data) {
    const b=data.batch, suffix='?batch_id='+encodeURIComponent(b.id);
    const table='<div class="scroll"><table><thead><tr><th>条件 / 格式 / 编码</th><th>有效 / 记录</th><th>负面解释</th><th>回避</th><th>完整分类</th></tr></thead><tbody>'+data.cells.map(c=>`<tr><td>${esc(c.condition)}<br>${esc(c.ablation_format==='unknown'?c.output_format:c.ablation_format)}<br>${esc(c.coder_version)}<br>${esc(c.source)}</td><td>${c.coded_n}/${c.recorded}</td><td>${c.interpretations.negative||0}/${c.coded_n}</td><td>${c.actions.avoid||0}/${c.coded_n}</td><td>${esc(pretty(c.interpretations))}<br>${esc(pretty(c.actions))}</td></tr>`).join('')+'</tbody></table></div>';
    return `<h3>${esc(b.id.slice(0,8))} · ${esc(b.models.join(', '))}</h3><p>${esc(b.protocols.join(', '))} · ${esc(b.sources.join(', '))}</p><p class="hint">${esc(data.measurement_note)}</p><div class="links"><a href="/api/history/export.json${suffix}">本批 JSON</a><a href="/api/history/export.csv${suffix}">本批 CSV</a></div>${table}<details><summary>原协议统计结果与运行状态</summary><pre>${esc(pretty({job:data.job,original_report:data.original_report,error:data.original_report_error,cells:data.cells}))}</pre></details><h4>逐次回答与实际发送的 Prompt（${data.records.length} 条）</h4>`+data.records.map(r=>`<details class="hist-record"><summary>${esc(r.id.slice(0,8))} · ${esc(r.condition)} · ${esc(r.ablation_format||r.output_format||'旧版')} · ${esc(r.status)} · ${esc((r.machine_coding||{}).interpretation||r.error||'未编码')}</summary><p>${esc(r.timestamp)} · ${esc(r.coder_version)}</p><pre>${esc(r.narrative||'没有返回原始回答')}</pre><p>自动编码与理由</p><pre>${esc(pretty(r.machine_coding))}</pre><details><summary>角色完整 Prompt</summary><pre>${esc(pretty(r.role_messages||null))}</pre></details><details><summary>编码器完整 Prompt / 原始输出</summary><pre>${esc(pretty({messages:r.evaluator_messages,raw:r.evaluator_raw}))}</pre></details><details><summary>模型参数、错误、配置及完整原始记录</summary><pre>${esc(pretty(r))}</pre></details></details>`).join('');
  }
  async function renderDetails() {
    const current=++generation;
    await Promise.all([['hist-selected','hist-detail'],['hist-compare','hist-comparison']].map(async ([select,target])=>{
      const id=$(select).value; $(target).textContent=id?'正在读取…':''; if(!id)return;
      try {const data=await api('/api/history/batch?batch_id='+encodeURIComponent(id)); if(current===generation)$(target).innerHTML=detailHTML(data);} catch(ex){if(current===generation)error(target,ex);}
    }));
  }
  $('hist-refresh').onclick=refresh;
  for(const key of ['from','to','model','protocol','source','status'])$('hist-'+key).onchange=renderList;
  $('hist-selected').onchange=renderDetails; $('hist-compare').onchange=renderDetails;
  $('hist-batches').onclick=e=>{const b=e.target.closest('[data-batch]');if(b){$('hist-selected').value=b.dataset.batch;renderDetails();}};
  $('hist-file').onchange=()=>{preview=null;importedDocument=null;$('hist-commit').disabled=true;};
  $('hist-preview').onclick=async()=>{
    $('hist-commit').disabled=true; preview=null;
    try {const file=$('hist-file').files[0];if(!file)throw new Error('请选择 JSON 文件');if(file.size>45000000)throw new Error('文件超过 45 MB，请拆为较小的完整记录数组');
      importedDocument=await file.text(); preview=await api('/api/history/import/preview',{document_json:importedDocument});
      $('hist-import-result').textContent=pretty(preview);$('hist-commit').disabled=preview.conflicts.length>0;
    }catch(ex){error('hist-import-result',ex);}
  };
  $('hist-commit').onclick=async()=>{
    if(!preview)return;$('hist-commit').disabled=true;
    try{const result=await api('/api/history/import/commit',{document_json:importedDocument,digest:preview.digest});$('hist-import-result').textContent=pretty(result);preview=null;await refresh();}
    catch(ex){error('hist-import-result',ex);}
  };
  function selectedVersion(){return versions.find(x=>x.version===$('prompt-version').value);}
  function showVersion(){const v=selectedVersion();if(!v)return;$('prompt-editor').value=pretty(v);$('prompt-info').textContent=v.version+' · SHA256 '+v.content_hash;
    $('prompt-export').href='/api/prompts/export.json?version='+encodeURIComponent(v.version);showDiff();}
  function showDiff(){try{const a=JSON.parse($('prompt-editor').value),b=versions.find(x=>x.version===$('prompt-compare').value);$('prompt-diff').textContent=pretty(Object.fromEntries(Object.keys(a).filter(k=>JSON.stringify(a[k])!==JSON.stringify(b?.[k])).map(k=>[k,{edited:a[k],comparison:b?.[k]}])));}catch(ex){error('prompt-diff',ex);}}
  async function loadVersions(select){const result=await api('/api/prompts');versions=result.versions;for(const id of ['prompt-version','prompt-compare'])$(id).innerHTML=versions.map(v=>option(v.version,v.name+' · '+v.version)).join('');if(select)$('prompt-version').value=select;if(versions.length>1)$('prompt-compare').value=versions[1].version;showVersion();}
  $('prompt-version').onchange=showVersion;$('prompt-compare').onchange=showDiff;$('prompt-editor').oninput=showDiff;
  $('prompt-preview').onclick=async()=>{try{const result=await api('/api/prompts/preview',{bundle:JSON.parse($('prompt-editor').value)});$('prompt-rendered').textContent=pretty(result);$('prompt-rendered').parentElement.open=true;$('prompt-status').textContent='模板验证通过；没有调用模型，也没有生成实验数据。';}catch(ex){error('prompt-status',ex);}};
  $('prompt-save').onclick=async()=>{try{const bundle=JSON.parse($('prompt-editor').value);bundle.parent=selectedVersion().version;const saved=await api('/api/prompts',bundle);await loadVersions(saved.version);$('prompt-status').textContent='已保存不可覆盖的新版本：'+saved.version;}catch(ex){error('prompt-status',ex);}};
  refresh();loadVersions().catch(ex=>error('prompt-status',ex));
})();
