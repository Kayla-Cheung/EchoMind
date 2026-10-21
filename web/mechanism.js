(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const core = ['state_none', 'state_mild', 'state_moderate'];
const meanings = {positive:'正面', neutral:'中性', negative:'负面', unclear:'未定'};
const actions = {approach:'主动', wait:'等待', avoid:'回避', other:'其他'};
const percent = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
const pp = value => value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} 个百分点`;
const pvalue = value => value == null ? '—' : value < .0001 ? value.toExponential(2) : value.toFixed(4);
let boot, report, activeJob, busy = false, previewSerial = 0, estimateSerial = 0, reportSerial = 0, toastTimer;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
  return data;
}
function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => $('toast').hidden = true, 8000);
}
function options(id, items, value, label, empty) {
  const node = $(id), previous = node.value;
  node.replaceChildren();
  if (empty !== undefined) node.add(new Option(empty, ''));
  for (const item of items) node.add(new Option(label(item), value(item)));
  if ([...node.options].some(x => x.value === previous)) node.value = previous;
}
const provider = id => boot.providers.find(p => p.id === id);
function spec(coder = false) {
  const id = $(coder ? 'evaluator' : 'provider').value;
  const model = $(coder ? 'evaluatorModel' : 'model').value.trim();
  return {provider:id, model,
    region:id === 'minimax' ? $(coder ? 'evaluatorRegion' : 'region').value : 'international',
    ...(id === 'deepseek' && model === 'deepseek-flash' ? {thinking:'disabled', temperature:coder ? 0 : 1} : {})};
}
function payload() {
  return {protocol:boot.protocol, mode:$('mode').value, models:[spec()], evaluator:spec(true),
    conditions:core, scenario_ids:[$('scenario').value], variants:[$('variant').value],
    repeats:Number($('repeats').value), max_calls:300, concurrency:3, timeout:90};
}
function materials() {
  const variant = $('variant').value;
  const descriptions = ['三段平稳 / 得到回应的经历', '一段不利 + 两段平稳经历', '三段不利社交经历'];
  $('stateCards').innerHTML = core.map((c, i) => {
    const memories = boot.materials.profiles.find(p => p.id === c).memories[variant];
    return `<article class="condition"><b>${esc(boot.labels[c])}</b><p>${descriptions[i]}</p>
      <details><summary>查看经历 · ${esc(variant)}</summary><ul>${memories.map(m => `<li>${esc(m)}</li>`).join('')}</ul></details></article>`;
  }).join('');
}
function scene() {
  $('situation').textContent = boot.materials.scenarios.find(s => s.id === $('scenario').value).situation;
  preview();
  estimate();
}
async function preview() {
  const serial = ++previewSerial;
  try {
    const result = await api('/api/mechanism/preview', {...payload(), conditions:[$('previewCondition').value]});
    if (serial === previewSerial) $('prompt').textContent = result.messages.map(m => `[${m.role}]\n${m.content}`).join('\n\n');
  } catch (error) { if (serial === previewSerial) $('prompt').textContent = error.message; }
}
async function estimate() {
  const serial = ++estimateSerial;
  try {
    const data = payload(), result = await api('/api/estimate', data);
    if (serial !== estimateSerial) return;
    $('run').textContent = `运行三组 × ${data.repeats} 次`;
    $('estimate').textContent = data.mode === 'mock'
      ? `${result.role_calls} 个 MOCK 试次，不调用 API。预设样例仅用于检查流程。`
      : `${result.role_calls} 次角色调用 + ${result.coding_calls} 次固定编码器调用，可能产生费用；失败重试另计（最多尝试 3 次）。`;
    $('run').disabled = busy;
  } catch (error) {
    if (serial === estimateSerial) { $('estimate').textContent = error.message; $('run').disabled = true; }
  }
}
function lock(locked) {
  busy = locked;
  $('configuration').disabled = locked;
  $('run').disabled = locked;
  $('cancel').hidden = !locked;
  $('cancel').disabled = false;
}
async function run() {
  if (busy) return;
  lock(true);
  try {
    const data = payload();
    if (data.mode === 'live') {
      for (const item of [...data.models, data.evaluator]) {
        if (!provider(item.provider).configured) throw Error(`${provider(item.provider).name} 尚未配置本机密钥`);
      }
    }
    const estimate = await api('/api/estimate', data);
    if (data.mode === 'live' && !confirm(`本次 ${estimate.role_calls} 次角色调用 + ${estimate.coding_calls} 次编码调用，可能收费，失败可能重试。按固定规则保留整批结果。开始？`)) {
      lock(false); return;
    }
    const job = await api('/api/jobs', data);
    activeJob = job.id;
    sessionStorage.setItem('sos.mechanism.job', activeJob);
    report = null;
    $('rates').replaceChildren();
    $('responses').innerHTML = '<div class="empty">整批完成后查看逐次回答。</div>';
    $('statistics').hidden = true;
    $('json').hidden = $('csv').hidden = true;
    $('batchContext').textContent = `当前批次 ${activeJob.slice(0, 8)} · ${data.mode === 'mock' ? 'MOCK' : '真实模型'}`;
    $('verdict').className = 'verdict insufficient';
    $('verdict').innerHTML = '<b>正在收集回答</b><p>整批结束后按预先固定的规则判断。</p>';
    poll();
  } catch (error) { lock(false); toast(error.message); }
}
async function poll() {
  if (!activeJob) return;
  try {
    const job = await api('/api/jobs/' + activeJob);
    $('progress').textContent = `已处理 ${job.completed}/${job.total} · 失败 ${job.failed}`;
    if (['complete', 'cancelled', 'error'].includes(job.status)) {
      const completedId = activeJob;
      activeJob = null;
      sessionStorage.removeItem('sos.mechanism.job');
      lock(false);
      $('progress').textContent += job.status === 'complete' ? ' · 已结束' : job.status === 'cancelled' ? ' · 已停止' : ' · ' + job.error;
      await refreshBatches(completedId);
      if (!$('batch').value) {
        $('verdict').innerHTML = '<b>本批次没有完成记录</b><p>尚未形成可分析的样本。</p>';
      }
      return;
    }
    setTimeout(poll, 900);
  } catch (error) {
    activeJob = null;
    sessionStorage.removeItem('sos.mechanism.job');
    lock(false);
    toast('任务状态读取失败；已保存记录可从批次列表查看。' + error.message);
    await refreshBatches();
  }
}
function distribution(values, counts, dictionary) {
  return `<div class="stack" aria-hidden="true">${Object.keys(dictionary).map(k => `<span class="${k}" style="width:${100 * (values[k] || 0)}%"></span>`).join('')}</div>
    <div class="legend">${Object.entries(dictionary).map(([k, name]) => `<span><i class="${k}"></i>${name} ${counts[k] || 0} · ${percent(values[k])}</span>`).join(' / ')}</div>`;
}
function metric(condition) {
  const x = report.conditions[condition];
  const interval = ci => ci ? `${percent(ci[0])} – ${percent(ci[1])}` : '—';
  return `<article class="metric"><h3>${esc(boot.labels[condition])}<span>完成 ${x.complete_n}/${report.repeats}</span></h3>
    <div class="metric-line">负面解释<b>${percent(x.negative_rate)}<span class="fraction">${x.interpretation_counts.negative || 0}/${x.complete_n}</span></b></div>
    <p class="interval">95% 区间 ${interval(x.negative_ci)}</p>
    ${distribution(x.interpretation, x.interpretation_counts, meanings)}
    <div class="metric-line">回避意向<b>${percent(x.avoid_rate)}<span class="fraction">${x.action_counts.avoid || 0}/${x.complete_n}</span></b></div>
    <p class="interval">95% 区间 ${interval(x.avoid_ci)}</p>
    ${distribution(x.action, x.action_counts, actions)}
    <div class="quality">失败 ${x.failed_n}（格式错误 ${x.format_error_n}）· 取消 ${x.cancelled_n} · 未定类 ${x.uncodable_n}<br>
    未提供说话 ${x.missing_speech_n} · 未提供行为 ${x.missing_behavior_n}</div></article>`;
}
function responses() {
  if (!report) return;
  const repeat = Number($('sample').value);
  $('responses').innerHTML = core.map(condition => {
    const row = report.records.find(r => r.condition === condition && r.repeat === repeat);
    if (!row) return `<article class="response"><h3>${esc(boot.labels[condition])}</h3><p class="hint">该次尚无记录。</p></article>`;
    const code = row.machine_coding;
    const channels = [['thought','内心想法'], ['speech','说话（可选）'], ['behavior','行为（可选）']];
    return `<article class="response"><h3>${esc(boot.labels[condition])} · 第 ${repeat} 次</h3>
      ${channels.map(([key, name]) => `<div class="channel"><b>${name}</b><p class="${row.channels?.[key] ? '' : 'missing'}">${esc(row.channels?.[key] || (row.status === 'complete' ? '未提供' : '尚无有效通道'))}</p></div>`).join('')}
      ${code ? `<div class="code">解释：${meanings[code.interpretation]} · 行为：${actions[code.action]}<p>${esc(code.coding_reason)}</p></div>` : `<p class="error">${esc(row.error || row.status)}</p>`}
      <details><summary>原始回答与本次上下文</summary><pre>${esc(row.narrative || '无回答')}</pre><pre>${esc(row.role_messages.map(m => `[${m.role}]\n${m.content}`).join('\n\n'))}</pre></details>
      </article>`;
  }).join('');
}
function renderReport() {
  const result = report;
  const kind = result.source === 'LIVE_LLM_API' ? '真实模型' : 'MOCK · 合成样例';
  $('batchContext').textContent = `${kind} · ${result.model} · 编码器 ${result.evaluator_model} · 材料 ${result.variant} · ${result.scenario.id} · 完成 ${result.complete_n}/${result.planned_n}`;
  $('verdict').className = 'verdict ' + result.verdict.status;
  $('verdict').innerHTML = `<b>${esc(result.verdict.title)}</b><p>${esc(result.verdict.reason)}</p><p>本批问题：${esc(result.scenario.situation)}</p>`;
  $('rates').innerHTML = core.map(metric).join('');
  $('denominator').hidden = false;
  $('statistics').hidden = false;
  $('comparison').innerHTML = `<div class="scroll"><table><tr><th>预设指标</th><th>不利 − 平稳</th><th>原始 p</th><th>校正后 p</th></tr>${result.comparisons.map(x => `<tr><td>${x.endpoint === 'negative' ? '负面解释' : '回避意向'}</td><td>${pp(x.delta)}</td><td>${result.source === 'LIVE_LLM_API' ? pvalue(x.p) : '—（MOCK）'}</td><td>${result.source === 'LIVE_LLM_API' ? pvalue(x.adjusted_p) : '—（MOCK）'}</td></tr>`).join('')}</table></div>`;
  $('allRecords').innerHTML = `<table><tr><th>提交顺序</th><th>经历条件</th><th>第几次</th><th>状态</th><th>解释</th><th>行动</th><th>失败原因</th></tr>${result.records.map(r => `<tr><td>${r.schedule_index}</td><td>${esc(boot.labels[r.condition])}</td><td>${r.repeat}</td><td>${esc(r.status)}</td><td>${meanings[r.machine_coding?.interpretation] || '—'}</td><td>${actions[r.machine_coding?.action] || '—'}</td><td>${esc(r.error || '—')}</td></tr>`).join('')}</table>`;
  options('sample', Array.from({length:result.repeats}, (_, i) => i + 1), x => x, x => `第 ${x} 次`);
  for (const format of ['csv', 'json']) {
    $(format).href = `/api/mechanism/export.${format}?batch_id=${encodeURIComponent(result.batch_id)}`;
    $(format).hidden = false;
  }
  responses();
}
async function loadReport() {
  if (!$('batch').value) return;
  const serial = ++reportSerial;
  try {
    const next = await api('/api/mechanism/report', {batch_id:$('batch').value});
    if (serial === reportSerial) { report = next; renderReport(); }
  } catch (error) { toast(error.message); }
}
async function refreshBatches(selected) {
  const latest = await api('/api/mechanism/bootstrap');
  options('batch', latest.batches, b => b.id,
    b => `${b.source === 'LIVE_LLM_API' ? '真实模型' : 'MOCK'} · ${b.model} · ${new Date(b.timestamp).toLocaleString()} · ${b.id.slice(0,8)}`,
    latest.batches.length ? undefined : '尚无记录');
  if (selected && latest.batches.some(b => b.id === selected)) $('batch').value = selected;
  await loadReport();
}
async function init() {
  try {
    boot = await api('/api/mechanism/bootstrap');
    $('connection').textContent = '本地服务已连接';
    $('identity').textContent = `${boot.identity.name} · ${boot.identity.description}`;
    $('claim').textContent = boot.rule.claim;
    for (const id of ['provider','evaluator']) {
      options(id, boot.providers, p => p.id, p => p.name + (p.configured ? '' : ' · 未配置'));
      $(id).value = boot.providers.find(p => p.configured)?.id || boot.providers[0].id;
    }
    $('model').value = provider($('provider').value).default_model;
    $('evaluatorModel').value = provider($('evaluator').value).default_model;
    options('scenario', boot.materials.scenarios, s => s.id, s => `${s.id} · ${s.situation.slice(0, 21)}…`);
    options('previewCondition', core, c => c, c => boot.labels[c]);
    $('provider').onchange = () => { $('model').value = provider($('provider').value).default_model; preview(); estimate(); };
    $('evaluator').onchange = () => { $('evaluatorModel').value = provider($('evaluator').value).default_model; estimate(); };
    $('scenario').onchange = scene;
    $('variant').onchange = () => { materials(); preview(); estimate(); };
    $('previewCondition').onchange = preview;
    for (const id of ['repeats','mode','model','evaluatorModel','region','evaluatorRegion']) $(id).onchange = () => { preview(); estimate(); };
    $('batch').onchange = loadReport;
    $('sample').onchange = responses;
    $('run').onclick = run;
    $('cancel').onclick = async () => {
      if (activeJob) try {
        await api('/api/jobs/' + activeJob + '/cancel', {});
        $('cancel').disabled = true;
        $('progress').textContent += ' · 正在结束已发出的调用…';
      } catch (error) { toast(error.message); }
    };
    materials(); scene();
    await refreshBatches();
    activeJob = sessionStorage.getItem('sos.mechanism.job');
    if (activeJob) { lock(true); poll(); }
  } catch (error) { $('connection').textContent = '连接失败'; toast(error.message); }
}
init();

})();
