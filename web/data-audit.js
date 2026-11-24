(() => {
  'use strict';

  const state = {
    tab: 'sources',
    inventory: null,
    reviews: [],
    roleFilter: 'primary',
    dbKey: null,
    tableName: null,
    offset: 0,
    limit: 40,
    rows: [],
    totalRows: 0,
    selected: null,        // { db, table, rowid, row_hash, detail }
    viewMode: 'readable',  // 'readable' | 'raw'
    decision: 'uncertain',
    coding: {
      threat_attribution: null,
      benign_attribution: null,
      memory_intrusion: null,
      behavioral_avoidance: null,
    },
    pairData: null,
    rrKey: null,
  };

  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function esc(v) {
    const d = document.createElement('div');
    d.textContent = v == null ? '' : String(v);
    return d.innerHTML;
  }

  function showError(msg) {
    const el = $('message');
    if (!msg) {
      el.textContent = '';
      el.classList.add('hidden');
    } else {
      el.textContent = msg;
      el.classList.remove('hidden');
    }
  }

  function toast(msg) {
    const el = $('toast');
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add('hidden'), 2600);
  }

  async function api(url, options) {
    const res = await fetch(url, { cache: 'no-store', ...options });
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function run(fn) {
    return async (...args) => {
      showError('');
      try {
        await fn(...args);
      } catch (err) {
        showError(err.message || String(err));
      }
    };
  }

  function downloadJson(name, obj) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function decisionBadge(dec) {
    if (dec === 'include') return '<span class="badge b-ok">建議納入</span>';
    if (dec === 'exclude') return '<span class="badge b-err">建議排除</span>';
    if (dec === 'uncertain') return '<span class="badge b-warn">待確認</span>';
    return '<span class="badge b-muted">未審</span>';
  }

  function flagLabel(f) {
    const map = {
      mixed_neutral_risk: '疑似混合歸因壓扁',
      s4_memory_spillover: 'S4 記憶溢出',
      cross_model_coder: '跨模型編碼',
      low_confidence: '低置信度',
      error_record: '異常/失敗',
      mock_record: 'MOCK',
      model_mismatch: '模型 ID 不符',
      missing_text: '缺失文本',
    };
    return map[f] || f;
  }

  function currentDbInfo() {
    return (state.inventory && state.inventory.databases || []).find((d) => d.key === state.dbKey) || null;
  }

  function switchTab(tab) {
    state.tab = tab;
    $$('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    $$('.view').forEach((v) => v.classList.toggle('active', v.id === `tab-${tab}`));
    if (tab === 'inspect' && state.dbKey && !state.rows.length) {
      run(loadRows)();
    }
    if (tab === 'pairs' && state.dbKey) {
      syncBatchDropdowns();
      run(loadPairs)();
    }
    if (tab === 'rr') {
      run(initRRTab)();
    }
    if (tab === 'exports') {
      syncBatchDropdowns();
    }
  }

  /* ===================== TOP KPI CARDS ===================== */
  function renderTopCards() {
    const inv = state.inventory;
    if (!inv) return;
    const items = [
      ['來源資料庫', inv.databases.length, `核心源庫 ${inv.databases.filter((d) => d.is_primary_source).length} 個`],
      ['跨檔案唯一 trial ID', inv.unique_trial_ids, '含 LIVE / MOCK / 失敗，不作合併樣本'],
      ['相同內容額外副本', inv.identical_extra_copies, '跨版本鏡像與備份重複數'],
      ['內容衝突 ID', inv.conflicts.length, inv.conflicts.length ? '需人工逐筆核查' : '0 衝突'],
      ['已保存審查事件', state.reviews.length, 'append-only 歷史庫'],
    ];
    $('cards').innerHTML = items.map(([lbl, val, sub]) => `
      <div class="card">
        <strong>${esc(val)}</strong>
        <div>${esc(lbl)}</div>
        <span>${esc(sub)}</span>
      </div>
    `).join('');
  }

  /* ===================== TAB 1: SOURCES ===================== */
  function filteredDbs() {
    const inv = state.inventory;
    if (!inv) return [];
    const q = $('dbSearch').value.trim().toLowerCase();
    return inv.databases.filter((d) => {
      if (state.roleFilter === 'primary' && !d.is_primary_source) return false;
      if (state.roleFilter === 'source' && d.role !== 'source') return false;
      if (state.roleFilter === 'backup' && d.role !== 'backup') return false;
      if (state.roleFilter === 'derived_recovery' && d.role !== 'derived_recovery') return false;
      if (state.roleFilter === 'rr' && !d.has_rr) return false;
      if (q && !d.path.toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function renderDbSelector() {
    const list = filteredDbs();
    const sel = $('database');
    sel.innerHTML = '';
    for (const d of list) {
      const opt = document.createElement('option');
      opt.value = d.key;
      const tSum = (d.tables || []).filter((t) => ['trials', 'episodes', 'ratings'].includes(t.name)).map((t) => `${t.name}:${t.n}`).join(', ');
      opt.textContent = `[${d.role}] ${d.path}${tSum ? ` (${tSum})` : ''}`;
      sel.appendChild(opt);
    }
    if (list.length) {
      sel.value = list.some((d) => d.key === state.dbKey) ? state.dbKey : list[0].key;
      chooseDb();
    } else {
      state.dbKey = null;
      $('dbMetaGrid').innerHTML = '<div class="muted">沒有匹配的資料庫。</div>';
      $('qualityHintBar').innerHTML = '';
      $('groups').innerHTML = '';
    }
  }

  function syncBatchDropdowns() {
    const d = currentDbInfo();
    const batches = [];
    const seen = new Set();
    for (const g of (d && d.groups) || []) {
      if (g.batch_id && !seen.has(g.batch_id)) {
        seen.add(g.batch_id);
        batches.push({ id: g.batch_id, label: `${g.batch_id.slice(0, 8)} · ${g.protocol} · ${g.source} (${g.n})` });
      }
    }
    const fill = (id, emptyLabel) => {
      const el = $(id);
      if (!el) return;
      const prev = el.value;
      el.innerHTML = `<option value="">${esc(emptyLabel)}</option>` +
        batches.map((b) => `<option value="${esc(b.id)}">${esc(b.label)}</option>`).join('');
      if (batches.some((b) => b.id === prev)) el.value = prev;
    };
    fill('fBatch', '全部批次');
    fill('pairBatchSel', '全部（建議選定單一批次）');
    fill('blindBatchSel', '當前庫全部 complete 試次');
  }

  function chooseDb() {
    state.dbKey = $('database').value;
    const d = currentDbInfo();
    if (!d) return;

    $('curDbPath').textContent = d.path;
    const tablesText = (d.tables || []).map((t) => `${t.name}: ${t.n}`).join(' / ') || '—';
    $('dbMetaGrid').innerHTML = d.error
      ? `<div class="meta-tile"><div class="k">讀取錯誤</div><div class="v">${esc(d.error)}</div></div>`
      : `
        <div class="meta-tile"><div class="k">來源類型與完整性</div><div class="v">${esc(d.role)} · ${esc((d.integrity || []).join(', '))} · WAL: ${d.wal_present ? '存在' : '無'}</div></div>
        <div class="meta-tile"><div class="k">資料表筆數</div><div class="v">${esc(tablesText)}</div></div>
        <div class="meta-tile"><div class="k">結構檢查異常</div><div class="v">${(d.issues || []).length} 筆${d.event_trial_ids_absent ? ` · 孤立事件 trial_id: ${d.event_trial_ids_absent}` : ''}</div></div>
        <div class="meta-tile"><div class="k">檔案 SHA-256（前 24 位）</div><div class="v mono">${esc((d.file_sha256 || '').slice(0, 24))}…</div></div>
      `;

    // Quality hint quick-jump buttons
    const hints = d.quality_hints || {};
    const hintOrder = ['mixed_neutral_risk', 's4_memory_spillover', 'cross_model_coder', 'low_confidence', 'error_record', 'mock_record'];
    const hintBtns = hintOrder
      .filter((k) => hints[k] > 0)
      .map((k) => `<button class="hint-btn" data-flag="${esc(k)}" type="button">${esc(flagLabel(k))}：${hints[k]} 筆 → 去排查</button>`);
    if (d.has_rr) {
      hintBtns.unshift(`<button class="btn btn-sm btn-primary" id="jumpRRBtn" type="button">在 RR 聯動視圖開啟此庫 →</button>`);
    }
    $('qualityHintBar').innerHTML = hintBtns.join('');
    $$('.hint-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        $('table').value = 'trials';
        state.tableName = 'trials';
        $('fBatch').value = '';
        $('fSource').value = btn.dataset.flag === 'mock_record' ? 'MOCK_NOT_LLM' : 'LIVE_LLM_API';
        $('fStatus').value = '';
        $('fFlag').value = btn.dataset.flag;
        $('fReview').value = '';
        $('query').value = '';
        state.offset = 0;
        switchTab('inspect');
        run(loadRows)();
      });
    });
    const jumpRR = $('jumpRRBtn');
    if (jumpRR) {
      jumpRR.addEventListener('click', () => {
        state.rrKey = d.key;
        switchTab('rr');
      });
    }

    // Batch groups table (interactive click-to-filter!)
    if (d.groups && d.groups.length) {
      $('groups').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>batch_id</th><th>protocol</th><th>source</th><th>model</th>
              <th>prompt_version</th><th>coder_version</th><th>筆數</th><th>狀態分布</th><th>快捷操作</th>
            </tr>
          </thead>
          <tbody>
            ${d.groups.map((g) => `
              <tr class="clickable batch-row" data-bid="${esc(g.batch_id)}">
                <td class="mono" title="${esc(g.batch_id)}">${esc(g.batch_id.slice(0, 12))}</td>
                <td class="mono">${esc(g.protocol)}</td>
                <td><span class="badge ${g.source === 'LIVE_LLM_API' ? 'b-ok' : 'b-warn'}">${esc(g.source)}</span></td>
                <td class="mono">${esc(g.model)}</td>
                <td class="mono">${esc(g.prompt_version)}</td>
                <td class="mono">${esc(g.coder_version)}</td>
                <td><strong>${g.n}</strong></td>
                <td class="mono">${esc(JSON.stringify(g.statuses))}</td>
                <td>
                  <button class="btn btn-sm btn-outline batch-inspect" data-bid="${esc(g.batch_id)}" type="button">審查</button>
                  <button class="btn btn-sm btn-ghost batch-pair" data-bid="${esc(g.batch_id)}" type="button">配對</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      $$('.batch-inspect').forEach((b) => {
        b.addEventListener('click', (e) => {
          e.stopPropagation();
          openBatchInInspect(b.dataset.bid);
        });
      });
      $$('.batch-pair').forEach((b) => {
        b.addEventListener('click', (e) => {
          e.stopPropagation();
          syncBatchDropdowns();
          $('pairBatchSel').value = b.dataset.bid;
          switchTab('pairs');
        });
      });
      $$('.batch-row').forEach((tr) => {
        tr.addEventListener('click', () => openBatchInInspect(tr.dataset.bid));
      });
    } else {
      $('groups').innerHTML = d.has_rr
        ? '<p class="muted">此為 RR 量表資料庫（無 trials 批次分層），請點上方「在 RR 聯動視圖開啟此庫」或切換至「逐條審查」檢視 episodes / requests / ratings。</p>'
        : '<p class="muted">無 trials 批次資料。</p>';
    }

    $('issues').textContent = JSON.stringify({
      issues: d.issues,
      event_trial_ids_absent: d.event_trial_ids_absent,
      rating_counts: d.rating_counts,
      invalid_ratings: d.invalid_ratings,
      episode_rating_counts: d.episode_rating_counts,
    }, null, 2);

    // Populate table dropdown
    const tSel = $('table');
    tSel.innerHTML = '';
    for (const t of d.tables || []) {
      const opt = document.createElement('option');
      opt.value = t.name;
      opt.textContent = `${t.name} (${t.n})`;
      tSel.appendChild(opt);
    }
    if (d.tables && d.tables.length) {
      tSel.value = d.tables.some((t) => t.name === 'trials')
        ? 'trials'
        : d.tables.some((t) => t.name === 'episodes')
          ? 'episodes'
          : d.tables[0].name;
      state.tableName = tSel.value;
    } else {
      state.tableName = null;
    }
    syncBatchDropdowns();
    updateTableFilterVisibility();
    state.rows = [];
    state.selected = null;
  }

  function openBatchInInspect(batchId) {
    $('table').value = 'trials';
    state.tableName = 'trials';
    updateTableFilterVisibility();
    syncBatchDropdowns();
    $('fBatch').value = batchId;
    $('fSource').value = '';
    $('fStatus').value = '';
    $('fFlag').value = '';
    $('fReview').value = '';
    $('query').value = '';
    state.offset = 0;
    switchTab('inspect');
    run(loadRows)();
  }

  function updateTableFilterVisibility() {
    const isTrials = state.tableName === 'trials';
    $('batchFilterWrap').classList.toggle('hidden', !isTrials);
    $('sourceFilterWrap').classList.toggle('hidden', !isTrials);
    $('flagFilterWrap').classList.toggle('hidden', !isTrials);
  }

  /* ===================== TAB 2: ROW INSPECTOR ===================== */
  async function loadRows(keepSelectedRowid = null) {
    if (!state.dbKey || !state.tableName) return;
    const p = new URLSearchParams({
      db: state.dbKey,
      table: state.tableName,
      offset: String(state.offset),
      limit: String(state.limit),
      query: $('query').value.trim(),
    });
    if (state.tableName === 'trials') {
      if ($('fBatch').value) p.set('batch_id', $('fBatch').value);
      if ($('fSource').value) p.set('source', $('fSource').value);
      if ($('fFlag').value) p.set('flag', $('fFlag').value);
    }
    if ($('fStatus').value) p.set('status', $('fStatus').value);
    if ($('fReview').value) p.set('review_status', $('fReview').value);

    const data = await api('/api/rows?' + p.toString());
    state.rows = data.rows;
    state.totalRows = data.total;
    renderRowList();

    if (state.rows.length) {
      const target = keepSelectedRowid && state.rows.some((r) => r._audit_rowid_ === keepSelectedRowid)
        ? keepSelectedRowid
        : state.rows[0]._audit_rowid_;
      await selectRowById(target);
    } else {
      state.selected = null;
      $('readableView').innerHTML = '<div class="empty-state">當前篩選條件下沒有符合的記錄。</div>';
      $('raw').textContent = '沒有記錄。';
      $('reviewHistoryList').textContent = '尚未選取記錄。';
      $('histCount').textContent = '0';
      $('rowHashShort').textContent = '';
    }
  }

  function renderRowList() {
    const start = state.totalRows === 0 ? 0 : state.offset + 1;
    const end = Math.min(state.offset + state.limit, state.totalRows);
    $('count').textContent = `共 ${state.totalRows} 筆符合`;
    $('pageText').textContent = `${start}–${end} / ${state.totalRows}`;
    $('prev').disabled = state.offset === 0;
    $('next').disabled = state.offset + state.limit >= state.totalRows;

    $('rows').innerHTML = state.rows.map((r) => {
      const rowid = r._audit_rowid_;
      const active = state.selected && state.selected.rowid === rowid;
      const pv = r._preview_;
      let head = `#${rowid}`;
      let snippet = '';
      let tags = [];
      if (pv) {
        head = `#${rowid} · ${pv.scenario_id || '—'} · ${pv.condition || '—'}`;
        snippet = pv.snippet || '(無回應內容)';
        if (r.source) tags.push(`<span class="badge ${r.source === 'LIVE_LLM_API' ? 'b-ok' : 'b-warn'}">${esc(r.source === 'LIVE_LLM_API' ? 'LIVE' : 'MOCK')}</span>`);
        if (r.status && r.status !== 'complete') tags.push(`<span class="badge b-err">${esc(r.status)}</span>`);
        if (pv.prompt_variant) tags.push(`<span class="badge b-info">${esc(pv.prompt_variant)}</span>`);
        if (pv.temporal_variant) tags.push(`<span class="badge b-info">${esc(pv.temporal_variant)}</span>`);
        if (pv.legacy_interpretation) tags.push(`<span class="badge b-muted">機:${esc(pv.legacy_interpretation)}</span>`);
        for (const f of (pv.flags || []).slice(0, 2)) {
          if (f !== 'mock_record') tags.push(`<span class="badge b-warn">${esc(flagLabel(f))}</span>`);
        }
      } else {
        const keys = Object.keys(r).filter((k) => !k.startsWith('_') && !k.endsWith('_json') && k !== 'payload').slice(0, 4);
        head = `#${rowid} · ${r.episode_id || r.id || r.key || state.tableName}`;
        snippet = keys.map((k) => `${k}=${r[k] ?? ''}`).join(' · ');
        if (r.status) tags.push(`<span class="badge ${r.status === 'complete' ? 'b-ok' : 'b-err'}">${esc(r.status)}</span>`);
      }
      if (r._review_coded_) tags.push('<span class="badge b-info">4維✓</span>');
      return `
        <div class="row-card ${active ? 'active' : ''}" data-rowid="${rowid}">
          <div class="row-card-top">
            <strong class="small">${esc(head)}</strong>
            ${decisionBadge(r._review_decision_)}
          </div>
          <div class="row-snippet">${esc(snippet)}</div>
          <div class="row-tags">${tags.join('')}</div>
        </div>
      `;
    }).join('');

    $$('.row-card').forEach((el) => {
      el.addEventListener('click', run(() => selectRowById(Number(el.dataset.rowid))));
    });
  }

  function expandRowForRaw(row) {
    const out = {};
    for (const [k, v] of Object.entries(row)) {
      try {
        out[k] = typeof v === 'string' && (/_json$/.test(k) || k === 'payload') ? JSON.parse(v) : v;
      } catch {
        out[k] = v;
      }
    }
    return out;
  }

  async function selectRowById(rowid) {
    const anchor = { db: state.dbKey, table: state.tableName, rowid };
    const data = await api('/api/row?' + new URLSearchParams({ db: anchor.db, table: anchor.table, rowid: String(rowid) }));
    state.selected = { ...anchor, row_hash: data.hash, detail: data };
    $$('.row-card').forEach((el) => el.classList.toggle('active', Number(el.dataset.rowid) === rowid));
    $('rowHashShort').textContent = `row SHA-256: ${data.hash.slice(0, 12)}…`;

    $('raw').textContent = JSON.stringify(expandRowForRaw(data.row), null, 2);
    renderReadableView(data);
    resetDecisionForm();
    renderRowReviewHistory();
  }

  function renderReadableView(data) {
    const v = data.view || { kind: 'generic' };
    const box = $('readableView');

    if (v.kind === 'trial') {
      const mc = v.machine_coding || {};
      const showRawNarr = v.narrative && v.narrative.trim() !== (v.interpretation || '').trim();
      box.innerHTML = `
        <div class="meta-strip">
          <span class="badge ${v.source === 'LIVE_LLM_API' ? 'b-ok' : 'b-warn'}">${esc(v.source)}</span>
          <span class="badge ${v.status === 'complete' ? 'b-ok' : 'b-err'}">${esc(v.status)}</span>
          <span class="badge b-info">${esc(v.protocol)}</span>
          <span class="badge b-muted">${esc(v.model)}${v.returned_model && v.returned_model !== v.model ? ` → ${esc(v.returned_model)}` : ''}</span>
          <span class="badge b-muted">條件：${esc(v.condition || '—')}</span>
          <span class="badge b-muted">情境：${esc(v.scenario_id || '—')} (${esc(v.scenario_kind || '—')})</span>
          ${v.prompt_variant ? `<span class="badge b-info">Prompt: ${esc(v.prompt_variant)}</span>` : ''}
          ${v.temporal_variant ? `<span class="badge b-info">時間: ${esc(v.temporal_variant)}</span>` : ''}
          ${v.ablation_format ? `<span class="badge b-muted">格式: ${esc(v.ablation_format)}</span>` : ''}
          ${(v.flags || []).map((f) => `<span class="badge b-warn">${esc(flagLabel(f))}</span>`).join('')}
        </div>
        ${v.error ? `<div class="evidence-box" style="border-color:#e5a5a5;background:#fdecec;"><div class="ev-label" style="color:#a42828;">錯誤訊息</div><div class="ev-body mono">${esc(v.error)}</div></div>` : ''}
        ${v.scenario_prompt ? `<div class="evidence-box subtle"><div class="ev-label">情境提示 (${esc(v.scenario_title || v.scenario_id)})</div><div class="ev-body">${esc(v.scenario_prompt)}</div></div>` : ''}
        ${v.interpretation ? `<div class="evidence-box"><div class="ev-label">Interpretation / Thought（解釋與想法）</div><div class="ev-body">${esc(v.interpretation)}</div></div>` : ''}
        ${v.speech ? `<div class="evidence-box"><div class="ev-label">Speech（言語回應）</div><div class="ev-body">${esc(v.speech)}</div></div>` : ''}
        ${v.action ? `<div class="evidence-box"><div class="ev-label">Action / Behavior（預定行動）</div><div class="ev-body">${esc(v.action)}</div></div>` : ''}
        ${showRawNarr ? `<div class="evidence-box"><div class="ev-label">原始 Narrative 欄位</div><div class="ev-body">${esc(v.narrative)}</div></div>` : ''}
        <div class="evidence-box machine">
          <div class="ev-label">舊機器自動編碼（非人工金標準）</div>
          <div>
            <strong>interpretation：</strong><span class="badge b-muted">${esc(mc.interpretation || '缺失')}</span>
            &nbsp; <strong>action：</strong><span class="badge b-muted">${esc(mc.action || '缺失')}</span>
            &nbsp; <strong>confidence：</strong><span class="mono">${mc.coding_confidence != null ? esc(mc.coding_confidence) : '—'}</span>
            &nbsp; <strong>coder：</strong><span class="mono">${esc(v.coder_model || '—')}</span>
          </div>
          ${mc.coding_reason ? `<div class="muted" style="margin-top:6px;">理由：${esc(mc.coding_reason)}</div>` : ''}
        </div>
        <div class="muted small mono" style="margin:6px 0;">
          id=${esc(v.id)} · batch=${esc(v.batch_id)} · timestamp=${esc(v.timestamp)}
        </div>
        ${v.role_messages ? `<details class="drawer"><summary>完整角色輸入 Role Messages</summary><pre>${esc(JSON.stringify(v.role_messages, null, 2))}</pre></details>` : ''}
        ${v.memory_snapshot ? `<details class="drawer"><summary>記憶快照 Memory Snapshot</summary><pre>${esc(JSON.stringify(v.memory_snapshot, null, 2))}</pre></details>` : ''}
        ${v.evaluator_messages || v.evaluator_raw ? `<details class="drawer"><summary>編碼器輸入與原始輸出</summary><pre>${esc(JSON.stringify({ evaluator_messages: v.evaluator_messages, evaluator_raw: v.evaluator_raw }, null, 2))}</pre></details>` : ''}
      `;
      return;
    }

    if (v.kind === 'rr_episode') {
      const ep = v.episode || {};
      box.innerHTML = `
        <div class="meta-strip">
          <span class="badge ${ep.status === 'complete' ? 'b-ok' : 'b-err'}">${esc(ep.status)}</span>
          <span class="badge b-info">${esc(ep.arm || ep.prompt_variant || 'default')}</span>
          <span class="badge b-muted">條件：${esc(ep.condition_id)}</span>
          <span class="badge b-muted">情境：${esc(ep.scenario_id || 'ALL_9')}</span>
          <span class="badge b-muted">評分數：${(v.ratings || []).length}</span>
        </div>
        ${ep.error ? `<div class="evidence-box" style="border-color:#e5a5a5;background:#fdecec;"><div class="ev-label" style="color:#a42828;">Episode Error</div><div class="ev-body mono">${esc(ep.error)}</div></div>` : ''}
        <div class="evidence-box">
          <div class="ev-label">關聯 Requests (${(v.requests || []).length})</div>
          ${(v.requests || []).map((rq) => `
            <details class="drawer">
              <summary>${esc(rq.phase)} · ${esc(rq.parse_status || rq.state)} · ${esc(rq.returned_model || rq.requested_model || '')}</summary>
              <pre>${esc(JSON.stringify({ response_id: rq.response_id, error: rq.error, raw_response: rq.raw_public_response || rq.raw_response, usage: rq.usage_json }, null, 2))}</pre>
            </details>
          `).join('')}
        </div>
        <div class="evidence-box">
          <div class="ev-label">關聯 Ratings 1–4 明細 (${(v.ratings || []).length})</div>
          <div class="scroll">
            <table>
              <thead><tr><th>item_id</th><th>scenario</th><th>type</th><th>rating (1–4)</th></tr></thead>
              <tbody>
                ${(v.ratings || []).map((rt) => `
                  <tr>
                    <td class="mono">${esc(rt.item_id)}</td>
                    <td class="mono">${esc(rt.scenario_id || '—')}</td>
                    <td class="mono">${esc(rt.rating_type || rt.item_type || '—')}</td>
                    <td><strong>${esc(rt.rating)}</strong></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
      return;
    }

    // Generic table readable key-value table
    const expanded = expandRowForRaw(data.row);
    box.innerHTML = `
      <div class="scroll">
        <table>
          <thead><tr><th>欄位</th><th>內容</th></tr></thead>
          <tbody>
            ${Object.entries(expanded).map(([k, val]) => `
              <tr>
                <td class="mono"><strong>${esc(k)}</strong></td>
                <td>${typeof val === 'object' && val !== null ? `<pre style="margin:0;max-height:240px;">${esc(JSON.stringify(val, null, 2))}</pre>` : esc(val)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function setViewMode(mode) {
    state.viewMode = mode;
    $('viewReadableBtn').classList.toggle('active', mode === 'readable');
    $('viewRawBtn').classList.toggle('active', mode === 'raw');
    $('readableView').classList.toggle('hidden', mode !== 'readable');
    $('raw').classList.toggle('hidden', mode !== 'raw');
  }

  /* ===================== REVIEW FORM ===================== */
  function setSeg(field, val) {
    if (field === 'decision') {
      state.decision = val;
      $('decision').value = val;
    } else {
      state.coding[field] = val;
    }
    const grp = document.querySelector(`.seg-group[data-field="${field}"]`);
    if (!grp) return;
    grp.querySelectorAll('.seg').forEach((b) => {
      const bVal = field === 'decision' ? b.dataset.val : Number(b.dataset.val);
      b.classList.toggle('selected', val !== null && bVal === val);
    });
  }

  function resetDecisionForm() {
    setSeg('decision', 'uncertain');
    for (const ax of ['threat_attribution', 'benign_attribution', 'memory_intrusion', 'behavioral_avoidance']) {
      setSeg(ax, null);
    }
    $('mixedCheck').checked = false;
    $('note').value = '';
  }

  function matchingReviewsForSelected() {
    if (!state.selected) return [];
    return state.reviews.filter(
      (r) => r.db === state.selected.db && r.table === state.selected.table && String(r.rowid) === String(state.selected.rowid)
    );
  }

  function renderRowReviewHistory() {
    const list = matchingReviewsForSelected();
    $('histCount').textContent = String(list.length);
    if (!list.length) {
      $('reviewHistoryList').innerHTML = '<div class="muted small">此列尚無審查紀錄。</div>';
      return;
    }
    $('reviewHistoryList').innerHTML = [...list].reverse().map((ev) => {
      const c = ev.coding;
      const cLine = c
        ? `<div class="muted small">4維：威${c.threat_attribution ?? '—'} · 良${c.benign_attribution ?? '—'} · 侵${c.memory_intrusion ?? '—'} · 避${c.behavioral_avoidance ?? '—'}${c.mixed_attribution ? ' · 混合歸因' : ''}</div>`
        : '';
      return `
        <div class="hist-card">
          <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
            <strong>${esc(ev.reviewer)}</strong>
            ${decisionBadge(ev.decision)}
          </div>
          <div style="margin:4px 0;">${esc(ev.note)}</div>
          ${cLine}
          <div class="muted small mono">${esc(ev.created_at)}</div>
        </div>
      `;
    }).join('');
  }

  function loadLatestIntoForm() {
    const list = matchingReviewsForSelected();
    if (!list.length) {
      toast('此列尚無歷史紀錄可帶入');
      return;
    }
    const last = list[list.length - 1];
    setSeg('decision', last.decision || 'uncertain');
    $('note').value = last.note || '';
    const c = last.coding || {};
    for (const ax of ['threat_attribution', 'benign_attribution', 'memory_intrusion', 'behavioral_avoidance']) {
      setSeg(ax, c[ax] != null ? c[ax] : null);
    }
    $('mixedCheck').checked = Boolean(c.mixed_attribution);
    toast('已帶入上次審查內容（保存時將追加新版本事件）');
  }

  async function saveReview(goNext = false) {
    if (!state.selected) throw new Error('請先選取一筆記錄');
    const reviewer = $('reviewer').value.trim();
    const note = $('note').value.trim();
    if (!reviewer || !note) throw new Error('請填寫審查者姓名／代號與證據依據');
    try { localStorage.setItem('echomind_audit_reviewer', reviewer); } catch {}

    const anyCoding = Object.values(state.coding).some((v) => v !== null) || $('mixedCheck').checked;
    const payload = {
      db: state.selected.db,
      table: state.selected.table,
      rowid: state.selected.rowid,
      row_hash: state.selected.row_hash,
      reviewer,
      decision: state.decision,
      note,
    };
    if (anyCoding) {
      payload.coding = { ...state.coding, mixed_attribution: $('mixedCheck').checked };
    }

    await api('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.reviews = await api('/api/reviews');
    renderTopCards();

    // Update current row status in list
    const rowObj = state.rows.find((r) => r._audit_rowid_ === state.selected.rowid);
    if (rowObj) {
      rowObj._review_decision_ = state.decision;
      rowObj._review_coded_ = Boolean(
        anyCoding && Object.values(state.coding).every((v) => v !== null)
      );
    }
    renderRowList();
    renderRowReviewHistory();
    toast('審查紀錄已追加保存（原始資料未改動）');
    if (goNext) {
      await stepRow(1);
    }
  }

  async function stepRow(delta) {
    if (!state.rows.length || !state.selected) return;
    const idx = state.rows.findIndex((r) => r._audit_rowid_ === state.selected.rowid);
    const nextIdx = idx + delta;
    if (nextIdx >= 0 && nextIdx < state.rows.length) {
      await selectRowById(state.rows[nextIdx]._audit_rowid_);
      const activeEl = document.querySelector('.row-card.active');
      if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
    } else if (delta > 0 && state.offset + state.limit < state.totalRows) {
      state.offset += state.limit;
      await loadRows();
    } else if (delta < 0 && state.offset > 0) {
      state.offset = Math.max(0, state.offset - state.limit);
      await loadRows();
    } else {
      toast(delta > 0 ? '已到本頁末尾' : '已到第一筆');
    }
  }

  /* ===================== TAB 3: PAIRS ===================== */
  async function loadPairs() {
    if (!state.dbKey) return;
    const d = currentDbInfo();
    if (!d || !(d.tables || []).some((t) => t.name === 'trials')) {
      $('pairSummary').innerHTML = '';
      $('pairList').innerHTML = '<div class="panel empty-state">當前資料庫不含 trials 表；請先在分頁 1 選擇 v0.3 / v0.4 / pilot / round3 等開放文本資料庫。</div>';
      return;
    }
    const p = new URLSearchParams({ db: state.dbKey, mode: $('pairModeSel').value });
    if ($('pairBatchSel').value) p.set('batch_id', $('pairBatchSel').value);
    const data = await api('/api/pairs?' + p.toString());
    state.pairData = data;
    renderPairs();
  }

  function renderPairSide(label, side) {
    if (!side) return `<div class="pair-arm"><strong class="badge b-err">${esc(label)} · 缺側（Missing Side）</strong></div>`;
    const rev = side.review;
    const revBadge = rev ? decisionBadge(rev.decision) : '<span class="badge b-muted">未審</span>';
    return `
      <div class="pair-arm">
        <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:6px;">
          <strong>${esc(label)}</strong>
          <div>
            <span class="badge b-muted">機:${esc(side.legacy_interpretation || '—')}/${esc(side.legacy_action || '—')}</span>
            ${revBadge}
            <button class="btn btn-sm btn-ghost pair-jump" data-rowid="${side.rowid}" type="button">檢查 #${side.rowid}</button>
          </div>
        </div>
        ${side.interpretation ? `<div><strong>解釋：</strong>${esc(side.interpretation)}</div>` : ''}
        ${side.speech ? `<div style="margin-top:4px;"><strong>言語：</strong>${esc(side.speech)}</div>` : ''}
        ${side.action ? `<div style="margin-top:4px;"><strong>行動：</strong>${esc(side.action)}</div>` : ''}
        ${!side.interpretation && side.narrative ? `<div>${esc(side.narrative)}</div>` : ''}
      </div>
    `;
  }

  function renderPairs() {
    const d = state.pairData;
    if (!d) return;
    const s = d.summary || {};
    $('pairSummary').innerHTML = `
      <div class="meta-tile"><div class="k">配對模式與依據</div><div class="v">${esc(d.left_label)} ↔ ${esc(d.right_label)}</div><div class="muted small">${esc(d.reason)}</div></div>
      <div class="meta-tile"><div class="k">完整配對 / 缺側 / 未配對</div><div class="v">${s.complete_pairs || 0} 完整 · ${s.missing_side_pairs || 0} 缺側 · ${s.unpaired_count || 0} 未配對</div></div>
      <div class="meta-tile"><div class="k">${esc(d.left_label)} 機器標籤</div><div class="v mono">${esc(JSON.stringify(s.left_legacy_interpretation || {}))}</div></div>
      <div class="meta-tile"><div class="k">${esc(d.right_label)} 機器標籤</div><div class="v mono">${esc(JSON.stringify(s.right_legacy_interpretation || {}))}</div></div>
    `;

    const onlyChanged = $('pairOnlyChanged').checked;
    const onlyMissing = $('pairOnlyMissing').checked;
    const items = (d.pairs || []).filter((p) => {
      if (onlyChanged && !p.label_changed) return false;
      if (onlyMissing && !p.missing_side) return false;
      return true;
    });

    $('pairList').innerHTML = items.length
      ? items.map((p) => `
          <div class="pair-card ${p.missing_side ? 'missing' : p.label_changed ? 'changed' : ''}">
            <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
              <div>
                <strong>${esc(p.condition)}</strong> · <span class="badge b-info">${esc(p.scenario_id)}</span>
                ${p.label_changed ? '<span class="badge b-warn">機器標籤變化</span>' : ''}
                ${p.missing_side ? `<span class="badge b-err">缺側: ${esc(p.missing_side)}</span>` : ''}
              </div>
              <span class="mono muted">${esc(p.pair_id)}</span>
            </div>
            <div class="pair-cols">
              ${renderPairSide(d.left_label, p.left)}
              ${renderPairSide(d.right_label, p.right)}
            </div>
          </div>
        `).join('')
      : '<div class="panel empty-state">當前條件下無配對結果（請確認選擇了對應批次與配對鍵）。</div>';

    $$('.pair-jump').forEach((btn) => {
      btn.addEventListener('click', run(async () => {
        const rid = Number(btn.dataset.rowid);
        $('table').value = 'trials';
        state.tableName = 'trials';
        updateTableFilterVisibility();
        $('fBatch').value = $('pairBatchSel').value || '';
        $('fSource').value = '';
        $('fStatus').value = '';
        $('fFlag').value = '';
        $('fReview').value = '';
        $('query').value = '';
        state.offset = 0;
        switchTab('inspect');
        await loadRows(rid);
        await selectRowById(rid);
      }));
    });
  }

  /* ===================== TAB 4: RR LINKED VIEW ===================== */
  async function initRRTab() {
    const rrDbs = (state.inventory && state.inventory.databases || []).filter((d) => d.has_rr);
    if (!rrDbs.length) {
      $('rrDbButtons').innerHTML = '';
      $('rrContainer').innerHTML = '<div class="empty-state">目前盤點未發現 RR 量表資料庫。</div>';
      return;
    }
    if (!state.rrKey || !rrDbs.some((d) => d.key === state.rrKey)) {
      const pref = rrDbs.find((d) => d.path.includes('rr-isolation-001')) || rrDbs[0];
      state.rrKey = pref.key;
    }
    $('rrDbButtons').innerHTML = rrDbs.map((d) => `
      <button class="pill rr-pick ${d.key === state.rrKey ? 'active' : ''}" data-key="${esc(d.key)}" type="button">${esc(d.path.split(/[\\/]/).pop())}</button>
    `).join('');
    $$('.rr-pick').forEach((b) => {
      b.addEventListener('click', run(async () => {
        state.rrKey = b.dataset.key;
        await initRRTab();
      }));
    });

    const data = await api('/api/rr-summary?' + new URLSearchParams({ db: state.rrKey }));
    renderRR(data);
  }

  function renderRR(d) {
    const req = d.requests_summary || {};
    const completeEps = (d.episodes || []).filter((e) => e.status === 'complete').length;

    const contrastHtml = (d.contrasts && d.contrasts.length)
      ? `
        <h3>配對 W1 差值（${esc(d.contrasts[0].delta_label)}，負值表示更接近人類分布）</h3>
        <div class="scroll">
          <table>
            <thead>
              <tr><th>條件</th><th>項數</th><th>${esc(d.contrasts[0].arm_a)} W1</th><th>${esc(d.contrasts[0].arm_b)} W1</th><th>全部項 ΔW1</th><th>社交項 ΔW1</th><th>改善 / 惡化 / 持平</th></tr>
            </thead>
            <tbody>
              ${d.contrasts.map((c) => `
                <tr>
                  <td><strong>${esc(c.condition_id)}</strong></td>
                  <td>${c.n_items}</td>
                  <td>${c.a_w1_mean}</td>
                  <td>${c.b_w1_mean}</td>
                  <td class="${c.delta_all_mean < 0 ? 'delta-neg' : c.delta_all_mean > 0 ? 'delta-pos' : ''}">${c.delta_all_mean > 0 ? '+' : ''}${c.delta_all_mean}</td>
                  <td class="${c.delta_social_mean < 0 ? 'delta-neg' : c.delta_social_mean > 0 ? 'delta-pos' : ''}">${c.delta_social_mean != null ? (c.delta_social_mean > 0 ? '+' : '') + c.delta_social_mean : '—'}</td>
                  <td>${c.improved} / ${c.worsened} / ${c.tied}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `
      : '';

    const cellsHtml = (d.cell_summaries && d.cell_summaries.length)
      ? `
        <h3>各臂 / 條件 1–4 評分分布與人類 W1 摘要</h3>
        <div class="scroll">
          <table>
            <thead><tr><th>臂 / 變體</th><th>條件</th><th>項數</th><th>全部項 W1</th><th>社交項 W1</th><th>零方差項</th><th>1 / 2 / 3 / 4 頻次</th></tr></thead>
            <tbody>
              ${d.cell_summaries.map((c) => `
                <tr>
                  <td><span class="badge b-info">${esc(c.axis)}</span></td>
                  <td><strong>${esc(c.condition_id)}</strong></td>
                  <td>${c.items}</td>
                  <td>${c.all_w1_mean ?? '—'}</td>
                  <td>${c.social_w1_mean ?? '—'}</td>
                  <td>${c.zero_variance_items}</td>
                  <td class="mono">${['1', '2', '3', '4'].map((k) => `${k}:${(c.freq || {})[k] || 0}`).join('  ')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `
      : '';

    $('rrContainer').innerHTML = `
      <div class="notice" style="margin-top:10px;">${esc(d.exploratory_notice)}</div>
      <div class="db-meta-grid">
        <div class="meta-tile"><div class="k">檔案路徑</div><div class="v mono">${esc(d.path)}</div></div>
        <div class="meta-tile"><div class="k">Episodes 完成</div><div class="v">${completeEps} / ${(d.episodes || []).length}</div></div>
        <div class="meta-tile"><div class="k">Ratings 總數</div><div class="v">${d.ratings_count}</div></div>
        <div class="meta-tile"><div class="k">Requests 狀態與模型</div><div class="v mono">${esc(JSON.stringify(req.by_state || {}))} · ${esc(JSON.stringify(req.by_model || {}))}</div></div>
      </div>
      ${contrastHtml}
      ${cellsHtml}
      <h3>Episodes 列表（點擊直接開啟聯動 requests + ratings 審查）</h3>
      <div class="scroll">
        <table>
          <thead><tr><th>#</th><th>episode_id</th><th>臂 / 變體</th><th>條件</th><th>情境</th><th>狀態</th><th>評分數</th><th>審查</th></tr></thead>
          <tbody>
            ${(d.episodes || []).map((ep) => `
              <tr class="clickable rr-ep-row" data-rowid="${ep.rowid}">
                <td class="mono">${ep.rowid}</td>
                <td class="mono">${esc(ep.episode_id)}</td>
                <td>${esc(ep.arm || ep.prompt_variant || 'default')}</td>
                <td>${esc(ep.condition_id)}</td>
                <td class="mono">${esc(ep.scenario_id)}</td>
                <td><span class="badge ${ep.status === 'complete' ? 'b-ok' : 'b-err'}">${esc(ep.status)}</span></td>
                <td>${ep.ratings_count}</td>
                <td>${decisionBadge(ep.review_decision)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

    $$('.rr-ep-row').forEach((tr) => {
      tr.addEventListener('click', run(async () => {
        const rid = Number(tr.dataset.rowid);
        state.roleFilter = 'all';
        $$('#rolePills .pill').forEach((p) => p.classList.toggle('active', p.dataset.role === 'all'));
        state.dbKey = d.db;
        renderDbSelector();
        $('table').value = 'episodes';
        state.tableName = 'episodes';
        updateTableFilterVisibility();
        state.offset = 0;
        switchTab('inspect');
        await loadRows(rid);
        await selectRowById(rid);
      }));
    });
  }

  /* ===================== BOOT & EVENTS ===================== */
  function bindEvents() {
    $$('.tab').forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.tab)));

    $$('#rolePills .pill').forEach((b) => {
      b.addEventListener('click', () => {
        state.roleFilter = b.dataset.role;
        $$('#rolePills .pill').forEach((p) => p.classList.toggle('active', p === b));
        renderDbSelector();
      });
    });

    $('dbSearch').addEventListener('input', renderDbSelector);
    $('database').addEventListener('change', chooseDb);
    $('openInspectBtn').addEventListener('click', () => {
      switchTab('inspect');
      run(loadRows)();
    });
    $('backSourcesBtn').addEventListener('click', () => switchTab('sources'));

    $('rescanBtn').addEventListener('click', run(async () => {
      state.inventory = await api('/api/rescan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      state.reviews = await api('/api/reviews');
      renderTopCards();
      renderDbSelector();
      toast('已完成只讀重新盤點');
    }));

    $('table').addEventListener('change', run(async () => {
      state.tableName = $('table').value;
      updateTableFilterVisibility();
      state.offset = 0;
      await loadRows();
    }));

    $('search').addEventListener('click', run(async () => { state.offset = 0; await loadRows(); }));
    $('query').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { state.offset = 0; run(loadRows)(); }
    });
    $('resetFilters').addEventListener('click', run(async () => {
      $('fBatch').value = '';
      $('fSource').value = '';
      $('fStatus').value = '';
      $('fFlag').value = '';
      $('fReview').value = '';
      $('query').value = '';
      state.offset = 0;
      await loadRows();
    }));
    $('prev').addEventListener('click', run(async () => { state.offset = Math.max(0, state.offset - state.limit); await loadRows(); }));
    $('next').addEventListener('click', run(async () => { state.offset += state.limit; await loadRows(); }));

    $('viewReadableBtn').addEventListener('click', () => setViewMode('readable'));
    $('viewRawBtn').addEventListener('click', () => setViewMode('raw'));
    $('prevRowBtn').addEventListener('click', run(() => stepRow(-1)));
    $('nextRowBtn').addEventListener('click', run(() => stepRow(1)));

    $$('.seg-group').forEach((grp) => {
      const field = grp.dataset.field;
      grp.querySelectorAll('.seg').forEach((btn) => {
        btn.addEventListener('click', () => {
          const val = field === 'decision' ? btn.dataset.val : Number(btn.dataset.val);
          if (field !== 'decision' && state.coding[field] === val) {
            setSeg(field, null);
          } else {
            setSeg(field, val);
          }
        });
      });
    });

    $$('.chip').forEach((ch) => {
      ch.addEventListener('click', () => {
        const cur = $('note').value.trim();
        $('note').value = cur ? `${cur} ${ch.dataset.note}` : ch.dataset.note;
        $('note').focus();
      });
    });

    $('save').addEventListener('click', run(() => saveReview(false)));
    $('saveNext').addEventListener('click', run(() => saveReview(true)));
    $('loadLastBtn').addEventListener('click', loadLatestIntoForm);

    document.addEventListener('keydown', (e) => {
      if (state.tab !== 'inspect') return;
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        run(() => saveReview(true))();
        return;
      }
      const tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'ArrowRight') { e.preventDefault(); run(() => stepRow(1))(); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); run(() => stepRow(-1))(); }
    });

    // Pairs
    $('loadPairsBtn').addEventListener('click', run(loadPairs));
    $('pairOnlyChanged').addEventListener('change', renderPairs);
    $('pairOnlyMissing').addEventListener('change', renderPairs);
    $('exportPairingCsvBtn').addEventListener('click', () => {
      if (!state.dbKey) return;
      const p = new URLSearchParams({ db: state.dbKey, mode: $('pairModeSel').value });
      if ($('pairBatchSel').value) p.set('batch_id', $('pairBatchSel').value);
      window.location.href = '/api/export/pairing.csv?' + p.toString();
    });

    // Exports
    const dlInv = () => downloadJson('echomind-inventory.json', state.inventory);
    $('exportInventory').addEventListener('click', dlInv);
    $('exportInventory2').addEventListener('click', dlInv);
    $('exportReviews').addEventListener('click', run(async () => downloadJson('echomind-reviews.json', await api('/api/reviews'))));
    $('exportReviewsCsv').addEventListener('click', () => { window.location.href = '/api/export/reviews.csv'; });

    const blindParams = () => {
      const p = new URLSearchParams({
        db: state.dbKey,
        source: $('blindSourceSel').value || 'LIVE_LLM_API',
        seed: $('blindSeedInput').value.trim() || 'echomind-blind-20261123',
      });
      if ($('blindBatchSel').value) p.set('batch_id', $('blindBatchSel').value);
      return p.toString();
    };
    $('dlBlindCsvBtn').addEventListener('click', () => {
      if (!state.dbKey) return showError('請先於分頁 1 選擇一個包含 trials 表的資料庫');
      window.location.href = '/api/export/blind-packet.csv?' + blindParams();
    });
    $('dlBlindMapBtn').addEventListener('click', () => {
      if (!state.dbKey) return showError('請先於分頁 1 選擇一個包含 trials 表的資料庫');
      window.location.href = '/api/export/blind-mapping.json?' + blindParams();
    });
  }

  run(async () => {
    try {
      const savedRev = localStorage.getItem('echomind_audit_reviewer');
      if (savedRev) $('reviewer').value = savedRev;
    } catch {}
    bindEvents();
    const [inv, revs] = await Promise.all([api('/api/inventory'), api('/api/reviews')]);
    state.inventory = inv;
    state.reviews = revs;
    renderTopCards();
    $('conflicts').textContent = JSON.stringify(inv.conflicts, null, 2);
    $('limits').textContent = (inv.limits || []).join('\n');
    renderDbSelector();
  })();
})();
