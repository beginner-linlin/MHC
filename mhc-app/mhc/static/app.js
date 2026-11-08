/* ============================================================
   MHC 预测工作台 — 前端逻辑
   ============================================================ */
(() => {
'use strict';

// ─────────────────────────── 常量 ───────────────────────────

const MODES = {
  pan: {
    title: 'MHC 结合预测',
    desc: '预测肽段与 HLA 分子的结合亲和力，输出 EL 得分、排名与结合等级。',
    needAllele: true,
    inputLabel: '多肽列表',
    placeholder: '每行一条肽，例如：\nSLYNTVATL\nGILGFVFTL\nMLLSVPLLL',
    acceptFasta: true,
  },
  chop: {
    title: '蛋白酶体切割预测',
    desc: '用 NetChop 预测蛋白酶体在蛋白序列上的切割位点，判断哪些肽段可能被真实产生。',
    needAllele: false,
    inputLabel: '蛋白 FASTA',
    placeholder: '粘贴蛋白序列，必须以 > 开头：\n>my_protein\nMLLSVPLLLGLLGAAACSSNCGSS',
    acceptFasta: true,
    forceFasta: true,
  },
  stab: {
    title: 'MHC 稳定性预测',
    desc: '用 NetMHCstabpan 预测肽-MHC 复合物的半衰期，即肽段在细胞表面能停留多久。',
    needAllele: true,
    inputLabel: '多肽列表',
    placeholder: '每行一条肽，例如：\nSLYNTVATL\nGILGFVFTL',
    acceptFasta: true,
  },
  pipeline: {
    title: '三步串联流水线',
    desc: '切割 → 结合 → 稳定性，一条流水线跑完，直接得到最可能被呈递的候选肽。',
    needAllele: true,
    inputLabel: '蛋白 FASTA',
    placeholder: '粘贴蛋白序列，必须以 > 开头：\n>my_protein\nMLLSVPLLLGLLGAAACSSNCGSS',
    acceptFasta: true,
    forceFasta: true,
  },
  mutant: {
    title: '突变肽筛选',
    desc: '对比参考与突变序列，找出突变产生的新肽段，并评估其免疫原性潜力。',
    needAllele: true,
    inputLabel: '序列对比',
    placeholder: '',
    acceptFasta: false,
  },
};

const SAMPLES = {
  pep: 'SLYNTVATL\nGILGFVFTL\nMLLSVPLLL\nRPSQRHGSK\nKLVALGINAV',
  fasta: '>EGFR_peptide\nMRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTFEDHFLSLQRMFNNCEVVLGNLEITYVQRNYDLSFLKTIQEVAGYVLIALNTVERIPLENLQIIRGNMYYENSYALAVLSNYDANKTGLKELPMRNLQEILHGAVRFSNNPALCNVESIQWRDIVSSDFLSNMSMDFQNHLGSCQKCDPSCPNGSCWGAGEENCQKLTKIICAQQCSGRCRGKSPSDCCHNQCAAGCTGPRESDCLVCRKFRDEATCKDTCPPLMLYNPTTYQMDVNPEGKYSFGATCVKKCPRNYVVTDHGSCVRACGADSYEMEEDGVRKCKKCEGPCRKVCNGIGIGEFKDSLSINATNIKHFKNCTSISGDLHILPVAFRGDSFTHTPPLDPQELDILKTVKEITGFLLIQAWPENRTDLHAFENLEIIRGRTKQHGQFSLAVVSLNITSLGLRSLKEISDGDVIISGNKNLCYANTINWKKLFGTSGQKTKIISNRGENSCKATGQVCHALCSPEGCWGPEPRDCVSCRNVSRGRECVDKCNLLEGEPREFVENSECIQCHPECLPQAMNITCTGRGPDNCIQCAHYIDGPHCVKTCPAGVMGENNTLVWKYADAGHVCHLCHPNCTYGCTGPGLEGCPTNGPKIPSIATGMVGALLLLLVVALGIGLFM',
  mutantRef: 'MRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTFEDHFLSLQRMFNNCEVVLGNLEITYVQRNYDLSFLKTIQEVAGYVLIALNTVERIPLENLQIIRGNMYYENSYALAVLSNYDANKTGLKELPMRNLQEILHGAVRFSNNPALCNVESIQWRDIVSSDFLSNMSMDFQNHLGSCQKCDPSCPNGSCWGAGEENCQKLTKIICAQQCSGRCRGKSPSDCCHNQCAAGCTGPRESDCLVCRKFRDEATCKDTCPPLMLYNPTTYQMDVNPEGKYSFGATCVKKCPRNYVVTDHGSCVRACGADSYEMEEDGVRKCKKCEGPCRKVCNGIGIGEFKDSLSINATNIKHFKNCTSISGDLHILPVAFRGDSFTHTPPLDPQELDILKTVKEITGFLLIQAWPENRTDLHAFENLEIIRGRTKQHGQFSLAVVSLNITSLGLRSLKEISDGDVIISGNKNLCYANTINWKKLFGTSGQKTKIISNRGENSCKATGQVCHALCSPEGCWGPEPRDCVSCRNVSRGRECVDKCNLLEGEPREFVENSECIQCHPECLPQAMNITCTGRGPDNCIQCAHYIDGPHCVKTCPAGVMGENNTLVWKYADAGHVCHLCHPNCTYGCTGPGLEGCPTNGPKIPSIATGMVGALLLLLVVALGIGLFM',
  mutantAlt: '',
};

// ─────────────────────────── 状态 ───────────────────────────

const state = {
  mode: 'pan',
  inputType: 'peptide',
  alleles: [],
  allAlleles: [],
  alleleTotal: 0,
  presets: { human: [], mouse: [] },
  currentJob: null,
  pollTimer: null,
  resultRows: [],
  resultKind: null,
  sortKey: null,
  sortDir: 1,
  historyOpen: false,
  params: {},
  mutLengths: [9],
  busy: false,
};

// ─────────────────────────── 工具函数 ───────────────────────────

const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};

function toast(msg, kind = '') {
  const t = el('div', 'toast ' + kind, msg);
  $('toastStack').appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity .25s, transform .25s';
    t.style.opacity = '0';
    t.style.transform = 'translateY(6px)';
    setTimeout(() => t.remove(), 260);
  }, kind === 'err' ? 5200 : 2800);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  let data;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    data = await res.json();
  } else {
    data = { ok: res.ok, text: await res.text() };
  }
  if (!res.ok || data.ok === false) {
    const msg = data.error || `请求失败 (HTTP ${res.status})`;
    throw new Error(msg);
  }
  return data;
}

const fmtNum = (v, digits = 3) => {
  if (v === null || v === undefined || v === '' || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 10000) return n.toFixed(0);
  if (Math.abs(n) >= 100) return n.toFixed(1);
  return n.toFixed(digits);
};

const bindTag = (b) => {
  const s = String(b || '');
  if (s.includes('SB')) return '<span class="tag sb">SB</span>';
  if (s.includes('WB')) return '<span class="tag wb">WB</span>';
  return '<span class="tag none">—</span>';
};

/** 排名越小越好；用颜色条直观表示（0 → 绿，>5 → 灰） */
function rankBar(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  const pct = Math.max(0, Math.min(1, 1 - Math.min(n, 10) / 10));
  const color = n < 0.5 ? '#16794a' : n < 2 ? '#d4a017' : '#cbd5e1';
  return `<div class="bar-cell"><span>${fmtNum(n)}</span>
    <div class="bar-track"><div class="bar-fill" style="width:${(pct * 100).toFixed(0)}%;background:${color}"></div></div></div>`;
}

// ─────────────────────────── 健康检查 ───────────────────────────

async function checkHealth() {
  const dot = $('healthDot');
  dot.className = 'status-dot loading';
  try {
    const d = await api('/api/health');
    dot.className = 'status-dot ok';
    dot.title = '服务正常';
    const t = d.tools || {};
    const short = (s) => String(s).replace(/^Net/, 'Net').slice(0, 40);
    $('versionInfo').innerHTML =
      `后端 v${d.app_version}<br>` +
      Object.entries(t).map(([k, v]) => `${k}: ${short(v)}`).join('<br>');
    $('historyBadge').textContent = d.history_count ?? 0;
  } catch (e) {
    dot.className = 'status-dot err';
    dot.title = '服务不可用：' + e.message;
    $('versionInfo').textContent = '服务不可用';
    toast('无法连接后端服务：' + e.message, 'err');
  }
}

// ─────────────────────────── 模式切换 ───────────────────────────

function setMode(mode) {
  if (state.busy) { toast('任务运行中，请等待完成或取消', 'err'); return; }
  state.mode = mode;
  const cfg = MODES[mode];

  document.querySelectorAll('.nav-item').forEach((b) => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });

  $('modeTitle').textContent = cfg.title;
  $('modeDesc').textContent = cfg.desc;

  // 突变模式：换掉主输入区
  const isMutant = mode === 'mutant';
  $('mutantBlock').hidden = !isMutant;
  document.querySelector('.field').style.display = isMutant ? 'none' : '';

  // 等位基因
  $('alleleField').style.display = cfg.needAllele ? '' : 'none';

  // 输入类型
  if (cfg.forceFasta) {
    setInputType('fasta');
    $('tabPeptide').disabled = true;
    $('tabPeptide').style.opacity = '.4';
  } else {
    $('tabPeptide').disabled = false;
    $('tabPeptide').style.opacity = '';
  }

  if (!isMutant) {
    $('inputText').placeholder = cfg.placeholder;
  }

  buildParams();
  updateInputStats();
  $('btnRunText').textContent = '开始预测';
}

function setInputType(t) {
  state.inputType = t;
  $('tabPeptide').classList.toggle('active', t === 'peptide');
  $('tabFasta').classList.toggle('active', t === 'fasta');
  $('tabFile').classList.remove('active');
  const ta = $('inputText');
  ta.placeholder = t === 'fasta'
    ? '粘贴蛋白序列，必须以 > 开头：\n>my_protein\nMLLSVPLLLGLLGAAACSSNCGSS'
    : MODES[state.mode].placeholder;
  updateInputStats();
}

// ─────────────────────────── 输入统计 ───────────────────────────

function analyzeInput() {
  const raw = $('inputText').value.trim();
  if (!raw) return { count: 0, kind: 'none', lengths: [], bad: [] };

  const isFasta = raw.startsWith('>');
  let seqs = [];
  let kind = 'peptide';

  if (isFasta) {
    kind = 'fasta';
    for (const line of raw.split('\n')) {
      if (line.startsWith('>') || !line.trim()) continue;
      const s = line.replace(/[^A-Za-z*\-]/g, '').toUpperCase().replace(/[-*]/g, '');
      if (s) seqs.push(s);
    }
  } else {
    for (const line of raw.split('\n')) {
      const s = line.trim().split(/[\s,;]+/)[0];
      if (!s || s.startsWith('#')) continue;
      const clean = s.replace(/[^A-Za-z*]/g, '').toUpperCase().replace(/\*$/, '');
      if (clean) seqs.push(clean);
    }
  }

  const lengths = kind === 'fasta' ? seqs.map((s) => s.length) : [...new Set(seqs.map((s) => s.length))].sort((a, b) => a - b);
  const bad = [...new Set(seqs.join('').replace(/[ACDEFGHIKLMNPQRSTVWY]/g, '').split(''))].filter(Boolean);

  return { count: seqs.length, kind, lengths, bad, seqs };
}

function updateInputStats() {
  const s = analyzeInput();
  const box = $('inputStats');
  if (!s.count) { box.textContent = '尚未输入'; return; }

  if (s.kind === 'fasta') {
    const total = s.lengths.reduce((a, b) => a + b, 0);
    const nine = s.lengths.reduce((a, L) => a + Math.max(0, L - 8), 0);
    box.textContent = `${s.count} 条蛋白 · 共 ${total} aa · 约 ${nine} 条 9mer`;
  } else {
    const lenTxt = s.lengths.join('/');
    box.textContent = `${s.count} 条肽 · 长度 ${lenTxt}`;
  }
  if (s.bad.length) {
    box.textContent += ` · ⚠ 非标准字符 ${s.bad.join('')}`;
    box.style.color = 'var(--red)';
  } else {
    box.style.color = '';
  }
}

// ─────────────────────────── 等位基因 ───────────────────────────

async function loadAlleles() {
  try {
    // 全量加载（10491 条，约 250KB），避免只加载前 2000 条导致 HLA-B/C 大量等位基因搜不到
    const d = await api('/api/alleles?limit=20000');
    state.allAlleles = d.alleles || [];
    state.alleleTotal = d.total || state.allAlleles.length;
    if (d.truncated) {
      console.warn(`等位基因列表被截断：已加载 ${state.allAlleles.length} / ${d.total}`);
    }
  } catch (e) {
    console.warn('等位基因列表加载失败', e);
  }
  try {
    const p = await api('/api/presets');
    state.presets = { human: p.human || [], mouse: p.mouse || [] };
    renderPresets();
  } catch (e) { /* 忽略 */ }
}

function renderPresets() {
  const box = $('presetRow');
  box.innerHTML = '';
  state.presets.human.slice(0, 8).forEach(([code, label]) => {
    const b = el('button', 'preset-btn', code.replace('HLA-', ''));
    b.title = label;
    if (state.alleles.includes(code)) b.classList.add('on');
    b.onclick = () => {
      const i = state.alleles.indexOf(code);
      if (i >= 0) state.alleles.splice(i, 1);
      else state.alleles.push(code);
      renderAlleles();
      renderPresets();
    };
    box.appendChild(b);
  });
}

function renderAlleles() {
  const box = $('alleleSelected');
  box.innerHTML = '';
  state.alleles.forEach((a) => {
    const t = el('span', 'allele-tag');
    t.appendChild(document.createTextNode(a.replace('HLA-', '')));
    const x = el('button', '', '×');
    x.title = '移除';
    x.onclick = () => {
      state.alleles = state.alleles.filter((z) => z !== a);
      renderAlleles();
      renderPresets();
    };
    t.appendChild(x);
    box.appendChild(t);
  });
  $('alleleCount').textContent = state.alleles.length
    ? `已选 ${state.alleles.length} 个`
    : '未选择';
  renderPresets();
}

function setupAlleleSearch() {
  const inp = $('alleleSearch');
  const dd = $('alleleDropdown');

  const show = () => {
    const q = inp.value.trim().toUpperCase();
    let items = state.allAlleles;
    if (q) {
      items = state.allAlleles.filter((a) => a.toUpperCase().includes(q));
      // 前缀匹配优先
      items.sort((a, b) => {
        const ai = a.toUpperCase().indexOf(q);
        const bi = b.toUpperCase().indexOf(q);
        return ai - bi || a.localeCompare(b);
      });
    }
    const list = items.slice(0, 80);
    dd.innerHTML = '';
    if (!list.length) {
      dd.appendChild(el('div', 'allele-empty', q ? '无匹配等位基因' : '加载中…'));
    } else {
      list.forEach((a) => {
        const o = el('div', 'allele-option' + (state.alleles.includes(a) ? ' disabled' : ''), a);
        if (!state.alleles.includes(a)) {
          o.onclick = () => {
            state.alleles.push(a);
            renderAlleles();
            inp.value = '';
            dd.hidden = true;
          };
        }
        dd.appendChild(o);
      });
    }
    dd.hidden = false;
  };

  inp.addEventListener('focus', show);
  inp.addEventListener('input', show);
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const first = dd.querySelector('.allele-option:not(.disabled)');
      if (first) first.click();
      else if (inp.value.trim()) {
        let v = inp.value.trim().toUpperCase().replace('*', '');
        if (!v.startsWith('HLA-') && /^[ABC]\d/.test(v)) v = 'HLA-' + v;
        const m = v.match(/^HLA-([ABC])(\d{2}):?(\d{2})$/);
        if (m) v = `HLA-${m[1]}${m[2]}:${m[3]}`;
        if (/^HLA-[ABC]\d{2}:\d{2}$/.test(v) && !state.alleles.includes(v)) {
          state.alleles.push(v);
          renderAlleles();
        }
        inp.value = '';
        dd.hidden = true;
      }
    } else if (e.key === 'Escape') {
      dd.hidden = true;
    }
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.allele-picker')) dd.hidden = true;
  });
}

// ─────────────────────────── 参数面板 ───────────────────────────

const PARAM_DEFS = {
  pan: [
    { key: 'with_ba', type: 'switch', label: '输出亲和力 (BA)', hint: '同时给出结合亲和力与 BA 排名', def: true },
    { key: 'sort', type: 'switch', label: '按亲和力排序', hint: '结果按结合由强到弱排列', def: false },
    { key: 'threshold', type: 'select', label: '输出阈值', hint: '只保留排名优于该值的肽', def: '0',
      options: [['0', '全部输出'], ['0.5', '仅强结合 (≤0.5%)'], ['2', '强+弱结合 (≤2%)'], ['5', '≤5%']] },
  ],
  chop: [
    { key: 'model', type: 'select', label: '预测模型', hint: '两种蛋白酶体模型的切割规律不同', def: '0',
      options: [['0', 'C 端 3.0（默认）'], ['1', '20S 3.0']] },
    { key: 'threshold', type: 'select', label: '切割阈值', hint: '越低越敏感，位点越多', def: '0.5',
      options: [['0.3', '0.3（宽松）'], ['0.5', '0.5（标准）'], ['0.7', '0.7（严格）'], ['0.9', '0.9（极严格）']] },
  ],
  stab: [
    { key: 'with_ia', type: 'switch', label: '同时输出亲和力', hint: '与 NetMHCpan 结果联动，给出综合评分', def: true },
    { key: 'sort', type: 'select', label: '排序方式', hint: '决定结果表默认顺序', def: '',
      options: [['', '不排序'], ['0', '按稳定性'], ['1', '按亲和力'], ['2', '按综合得分']] },
  ],
  pipeline: [
    { key: 'cleavage_threshold', type: 'select', label: '切割阈值', hint: '决定哪些位置算作切割位点', def: '0.5',
      options: [['0.3', '0.3（宽松，位点多）'], ['0.5', '0.5（标准）'], ['0.7', '0.7（严格）']] },
    { key: 'cleavage_model', type: 'select', label: '切割模型', hint: 'C 端 3.0 或 20S 3.0', def: '0',
      options: [['0', 'C 端 3.0'], ['1', '20S 3.0']] },
    { key: 'lengths', type: 'lengths', label: '肽长', hint: '生成的候选肽长度', def: [9] },
    { key: 'use_cleavage_filter', type: 'switch', label: '只在切割位点取肽', hint: '关掉则用全滑窗，候选更多但更慢', def: true },
    { key: 'max_rank_el', type: 'select', label: '结合筛选阈值', hint: '只保留 EL 排名优于该值的肽', def: '2',
      options: [['0.5', '强结合 (≤0.5%)'], ['2', '强+弱 (≤2%)'], ['5', '≤5%'], ['0', '不过滤']] },
    { key: 'min_thalf', type: 'number', label: '最小半衰期 (h)', hint: '0 表示不限制', def: 0, step: 0.5, min: 0 },
  ],
  mutant: [
    { key: 'max_rank_el', type: 'select', label: '结合筛选阈值', hint: '只保留 EL 排名优于该值的肽', def: '2',
      options: [['0.5', '强结合 (≤0.5%)'], ['2', '强+弱 (≤2%)'], ['5', '≤5%'], ['0', '不过滤']] },
  ],
};

function buildParams() {
  const box = $('paramsPanel');
  box.innerHTML = '';
  state.params = {};
  const defs = PARAM_DEFS[state.mode] || [];

  defs.forEach((d) => {
    state.params[d.key] = d.def;
    const row = el('div', 'param-row');
    const lab = el('div', 'param-label');
    lab.appendChild(el('strong', '', d.label));
    if (d.hint) lab.appendChild(el('em', '', d.hint));
    row.appendChild(lab);

    const ctl = el('div', 'param-control');

    if (d.type === 'switch') {
      const sw = el('button', 'switch' + (d.def ? ' on' : ''));
      sw.type = 'button';
      sw.onclick = () => {
        const on = !sw.classList.contains('on');
        sw.classList.toggle('on', on);
        state.params[d.key] = on;
      };
      ctl.appendChild(sw);
    } else if (d.type === 'select') {
      const sel = el('select');
      d.options.forEach(([v, t]) => {
        const o = el('option', '', t);
        o.value = v;
        if (String(d.def) === String(v)) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = () => {
        const v = sel.value;
        state.params[d.key] = (v === '' || v === '0' && d.key === 'threshold') ? v : v;
      };
      ctl.appendChild(sel);
    } else if (d.type === 'number') {
      const inp = el('input');
      inp.type = 'number';
      inp.value = d.def;
      if (d.step) inp.step = d.step;
      if (d.min !== undefined) inp.min = d.min;
      inp.oninput = () => { state.params[d.key] = Number(inp.value) || 0; };
      ctl.appendChild(inp);
    } else if (d.type === 'lengths') {
      const wrap = el('div', 'len-picker');
      [8, 9, 10, 11].forEach((L) => {
        const b = el('button', 'len' + (d.def.includes(L) ? ' active' : ''), String(L));
        b.type = 'button';
        b.onclick = () => {
          let cur = state.params[d.key] || [];
          if (cur.includes(L)) {
            if (cur.length === 1) { toast('至少保留一个肽长', 'err'); return; }
            cur = cur.filter((x) => x !== L);
          } else {
            cur = [...cur, L].sort((a, b) => a - b);
          }
          state.params[d.key] = cur;
          wrap.querySelectorAll('.len').forEach((x) => {
            x.classList.toggle('active', cur.includes(Number(x.textContent)));
          });
        };
        wrap.appendChild(b);
      });
      ctl.appendChild(wrap);
    }

    row.appendChild(ctl);
    box.appendChild(row);
  });
}

// ─────────────────────────── 任务提交 ───────────────────────────

async function runJob() {
  if (state.busy) return;
  const cfg = MODES[state.mode];

  // 收集参数
  const payload = { alleles: state.alleles };

  if (state.mode !== 'mutant') {
    const raw = $('inputText').value.trim();
    if (!raw) { toast('请先输入序列', 'err'); return; }
    payload.input = raw;
    payload.input_mode = state.inputType;
  } else {
    payload.ref_seq = $('refSeq').value.trim().toUpperCase();
    payload.alt_seq = $('altSeq').value.trim().toUpperCase();
    if (!payload.ref_seq || !payload.alt_seq) {
      toast('请填写参考序列与突变序列', 'err'); return;
    }
    if (payload.ref_seq.length !== payload.alt_seq.length) {
      toast(`两条序列长度不一致（${payload.ref_seq.length} vs ${payload.alt_seq.length}）`, 'err');
      return;
    }
    payload.peptide_lengths = state.mutLengths;
  }

  if (cfg.needAllele && !state.alleles.length) {
    toast('请至少选择一个 HLA 等位基因', 'err');
    $('alleleSearch').focus();
    return;
  }

  // 参数映射
  const p = state.params;
  if (state.mode === 'pan') {
    payload.with_ba = !!p.with_ba;
    payload.sort = !!p.sort;
    payload.threshold = p.threshold === '0' ? null : Number(p.threshold);
  } else if (state.mode === 'chop') {
    payload.model = Number(p.model);
    payload.threshold = Number(p.threshold);
  } else if (state.mode === 'stab') {
    payload.with_ia = !!p.with_ia;
    payload.sort = p.sort === '' ? null : Number(p.sort);
  } else if (state.mode === 'pipeline') {
    payload.cleavage_threshold = Number(p.cleavage_threshold);
    payload.cleavage_model = Number(p.cleavage_model);
    payload.peptide_lengths = p.lengths || [9];
    payload.use_cleavage_filter = !!p.use_cleavage_filter;
    payload.max_rank_el = Number(p.max_rank_el);
    payload.min_thalf = Number(p.min_thalf) || 0;
  } else if (state.mode === 'mutant') {
    payload.max_rank_el = Number(p.max_rank_el);
  }

  setBusy(true);
  hideAlert();

  try {
    // 先预检（校验规则随模式不同：netchop 不受肽长限制，netMHCpan 要求 ≥8）
    if (state.mode !== 'mutant') {
      const v = await api('/api/validate/input', {
        method: 'POST',
        body: JSON.stringify({
          input: payload.input,
          input_mode: payload.input_mode,
          alleles: state.alleles,
          mode: state.mode,
          min_peptide_len: state.mode === 'pipeline'
            ? Math.min(...(state.params.lengths || [9]))
            : 9,
        }),
      });
      const errs = (v.warnings || []).filter((w) => w.level === 'error');
      if (errs.length) {
        showAlert(errs.map((w) => w.message), 'error');
        toast('输入存在问题，请查看提示', 'err');
        setBusy(false);
        return;
      }
      const warns = (v.warnings || []).filter((w) => w.level === 'warn');
      if (warns.length) showAlert(warns.map((w) => w.message), 'warn');
    }

    const res = await api(`/api/jobs/${state.mode}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    state.currentJob = res.job;
    startPolling(res.job.id);
  } catch (e) {
    toast(e.message, 'err');
    showAlert([e.message], 'error');
    setBusy(false);
  }
}

function setBusy(b) {
  state.busy = b;
  $('btnRun').disabled = b;
  $('btnRunText').textContent = b ? '运行中…' : '开始预测';
  $('btnRun').querySelector('.btn-spinner').hidden = !b;
  $('btnCancel').hidden = !b;
  $('progressWrap').hidden = !b;

  if (!b) {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  } else {
    $('progressFill').style.width = '2%';
    $('progressStage').textContent = '准备中';
    $('progressMsg').textContent = '';
  }
}

// ─────────────────────────── 轮询 ───────────────────────────

function startPolling(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);

  $('progressWrap').hidden = false;
  $('stepsBox').hidden = true;
  $('kpiBox').hidden = true;
  $('tableToolbar').hidden = true;
  $('resultTable').hidden = true;
  $('emptyState').hidden = false;
  $('emptyState').querySelector('h3').textContent = '正在计算…';
  $('emptyState').querySelector('p').textContent = '结果会在完成后自动显示';
  $('resultSub').textContent = '任务运行中';
  $('resultActions').hidden = true;

  const tick = async () => {
    try {
      const d = await api(`/api/jobs/${jobId}`);
      const job = d.job;
      state.currentJob = job;

      $('progressFill').style.width = `${Math.round((job.progress || 0) * 100)}%`;
      $('progressStage').textContent = job.stage || '运行中';
      $('progressMsg').textContent = job.message || '';

      if (job.status === 'done') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        setBusy(false);
        $('progressWrap').hidden = true;
        renderResult(job);
        refreshHistoryBadge();
      } else if (job.status === 'failed') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        setBusy(false);
        $('progressWrap').hidden = true;
        showFailure(job);
        refreshHistoryBadge();
      } else if (job.status === 'cancelled') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        setBusy(false);
        $('progressWrap').hidden = true;
        toast('任务已取消');
        resetResultPanel('任务已取消');
        refreshHistoryBadge();
      }
    } catch (e) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      setBusy(false);
      toast('查询任务状态失败：' + e.message, 'err');
    }
  };

  tick();
  state.pollTimer = setInterval(tick, 450);
}

function showFailure(job) {
  let msg = job.error || '任务失败';
  try {
    const parsed = JSON.parse(msg);
    if (parsed.message) msg = parsed.message;
  } catch (e) { /* 保持原文 */ }

  $('emptyState').hidden = false;
  $('emptyState').querySelector('h3').textContent = '运行失败';
  $('emptyState').querySelector('p').textContent = msg.split('\n')[0];
  $('resultSub').textContent = '失败';
  showAlert([msg.split('\n').slice(0, 6).join('\n')], 'error');
  toast('任务失败：' + msg.split('\n')[0], 'err');
}

function resetResultPanel(sub) {
  $('emptyState').hidden = false;
  $('emptyState').querySelector('h3').textContent = '尚无结果';
  $('emptyState').querySelector('p').textContent = sub || '在左侧输入序列并点击「开始预测」';
  $('resultTable').hidden = true;
  $('kpiBox').hidden = true;
  $('stepsBox').hidden = true;
  $('tableToolbar').hidden = true;
  $('resultActions').hidden = true;
  $('resultSub').textContent = sub || '提交任务后在此查看';
}

// ─────────────────────────── 结果渲染 ───────────────────────────

const COLUMNS = {
  pan: [
    { key: 'pos', label: '位置', cls: 'numeric', w: 54 },
    { key: 'mhc', label: 'MHC', cls: 'mono' },
    { key: 'peptide', label: '肽段', cls: 'mono', strong: true },
    { key: 'identity', label: '来源蛋白', cls: 'mono' },
    { key: 'score_el', label: 'EL 得分', cls: 'numeric', num: true },
    { key: 'rank_el', label: 'EL 排名%', cls: 'numeric', render: rankBar },
    { key: 'score_ba', label: 'BA 得分', cls: 'numeric', num: true },
    { key: 'rank_ba', label: 'BA 排名%', cls: 'numeric', num: true },
    { key: 'aff_nm', label: '亲和力 nM', cls: 'numeric', num: true },
    { key: 'bind', label: '结合', render: bindTag },
  ],
  chop: [
    { key: 'protein', label: '蛋白', cls: 'mono' },
    { key: 'pos', label: '位置', cls: 'numeric', w: 54 },
    { key: 'aa', label: '残基', cls: 'mono' },
    { key: 'cleavage', label: '判定', render: (v) => v === 'S'
        ? '<span class="tag cut">切割</span>' : '<span class="tag keep">保留</span>' },
    { key: 'score', label: '切割概率', cls: 'numeric', num: true },
  ],
  stab: [
    { key: 'pos', label: '位置', cls: 'numeric', w: 54 },
    { key: 'hla', label: 'HLA', cls: 'mono' },
    { key: 'peptide', label: '肽段', cls: 'mono', strong: true },
    { key: 'identity', label: '来源蛋白', cls: 'mono' },
    { key: 'pred', label: '稳定性得分', cls: 'numeric', num: true },
    { key: 'thalf', label: '半衰期 h', cls: 'numeric', num: true },
    { key: 'rank_stab', label: '稳定性排名%', cls: 'numeric', render: rankBar },
    { key: 'l50', label: '1-log50k', cls: 'numeric', num: true },
    { key: 'aff', label: '亲和力 nM', cls: 'numeric', num: true },
    { key: 'rank_aff', label: '亲和力排名%', cls: 'numeric', num: true },
    { key: 'combined', label: '综合得分', cls: 'numeric', num: true },
    { key: 'combined_rank', label: '综合排名%', cls: 'numeric', num: true },
    { key: 'bind', label: '结合', render: bindTag },
  ],
  pipeline: [
    { key: 'protein', label: '蛋白', cls: 'mono' },
    { key: 'cut_pos', label: '切割位点', cls: 'numeric', w: 80 },
    { key: 'cut_score', label: '切割概率', cls: 'numeric', num: true },
    { key: 'peptide', label: '候选肽', cls: 'mono', strong: true },
    { key: 'mhc', label: 'HLA', cls: 'mono' },
    { key: 'rank_el', label: 'EL 排名%', cls: 'numeric', render: rankBar },
    { key: 'aff_nm', label: '亲和力 nM', cls: 'numeric', num: true },
    { key: 'bind_pan', label: '结合', render: bindTag },
    { key: 'thalf', label: '半衰期 h', cls: 'numeric', num: true },
    { key: 'rank_stab', label: '稳定性排名%', cls: 'numeric', render: rankBar },
    { key: 'combined_rank', label: '综合排名%', cls: 'numeric', num: true },
  ],
  mutant: [
    { key: 'pos', label: '肽起点', cls: 'numeric', w: 70 },
    { key: 'peptide', label: '突变肽', cls: 'mono', strong: true },
    { key: 'ref_peptide', label: '野生型肽', cls: 'mono' },
    { key: 'mutation', label: '突变', cls: 'mono' },
    { key: 'mhc', label: 'HLA', cls: 'mono' },
    { key: 'rank_el', label: 'EL 排名%', cls: 'numeric', render: rankBar },
    { key: 'aff_nm', label: '亲和力 nM', cls: 'numeric', num: true },
    { key: 'bind_pan', label: '结合', render: bindTag },
    { key: 'thalf', label: '半衰期 h', cls: 'numeric', num: true },
    { key: 'rank_stab', label: '稳定性排名%', cls: 'numeric', render: rankBar },
  ],
};

function renderResult(job) {
  const r = job.result || {};
  const kind = job.kind === 'mutant' ? 'mutant' : job.kind;
  state.resultKind = kind;
  state.resultRows = r.rows || [];
  state.sortKey = null;
  state.sortDir = 1;

  // 标题随任务类型变化
  const TITLES = {
    pan: '结合预测结果',
    chop: '切割位点',
    stab: '稳定性结果',
    pipeline: '流水线结果',
    mutant: '突变肽筛选结果',
  };
  $('resultTitle').textContent = TITLES[kind] || '结果';

  // 步骤条
  if (kind === 'pipeline' && r.steps) {
    renderSteps(r.steps, true);
    $('stepsBox').hidden = false;
  } else {
    $('stepsBox').hidden = true;
  }

  // KPI
  renderKpis(kind, r, job);

  // 元信息
  const n = state.resultRows.length;
  $('resultSub').textContent =
    `${n} 行结果 · 耗时 ${job.seconds ? job.seconds.toFixed(1) : '?'} 秒` +
    (r.candidates ? ` · 候选肽 ${r.candidates}` : '');

  if (!n) {
    $('emptyState').hidden = false;
    $('emptyState').querySelector('h3').textContent = '没有符合条件的结果';
    $('emptyState').querySelector('p').textContent =
      '可以放宽筛选阈值、降低切割阈值，或改用全滑窗模式再试';
    $('resultTable').hidden = true;
    $('tableToolbar').hidden = true;
    $('resultActions').hidden = false;
    return;
  }

  $('emptyState').hidden = true;
  $('resultTable').hidden = false;
  $('tableToolbar').hidden = false;
  $('resultActions').hidden = false;
  $('tableSearch').value = '';
  $('tableFilter').value = 'all';

  renderTable();
}

function renderSteps(steps, done) {
  const box = $('stepsBox');
  box.innerHTML = '';
  steps.forEach((s, i) => {
    const d = el('div', 'step ' + (done ? 'done' : 'active'));
    d.appendChild(el('div', 'step-dot', done ? '✓' : String(i + 1)));
    const info = el('div', 'step-info');
    info.appendChild(el('strong', '', s.label));
    const detail = `${s.rows_in} → ${s.rows_out}` + (s.seconds ? ` · ${s.seconds}s` : '');
    info.appendChild(el('em', '', s.note || detail));
    d.appendChild(info);
    box.appendChild(d);
  });
}

function renderKpis(kind, r, job) {
  const box = $('kpiBox');
  box.innerHTML = '';
  const add = (label, value, unit, cls) => {
    const k = el('div', 'kpi');
    k.appendChild(el('div', 'kpi-label', label));
    const v = el('div', 'kpi-value ' + (cls || ''));
    v.appendChild(document.createTextNode(value));
    if (unit) v.appendChild(el('span', 'kpi-unit', unit));
    k.appendChild(v);
    box.appendChild(k);
  };

  const rows = r.rows || [];
  const summary = r.summary || {};

  if (kind === 'pan') {
    const sb = rows.filter((x) => String(x.bind).includes('SB')).length;
    const wb = rows.filter((x) => String(x.bind).includes('WB')).length;
    add('结果行数', rows.length);
    add('强结合 SB', sb, '', 'green');
    add('弱结合 WB', wb, '', 'amber');
    add('最佳排名', fmtNum(Math.min(...rows.map((x) => Number(x.rank_el) || 999))), '%', 'purple');
  } else if (kind === 'chop') {
    const sites = rows.filter((x) => x.cleavage === 'S').length;
    add('蛋白数', (r.summary || []).length || new Set(rows.map((x) => x.protein)).size);
    add('切割位点', sites, '', 'green');
    add('残基总数', rows.length);
    add('切割率', ((sites / Math.max(rows.length, 1)) * 100).toFixed(1), '%');
  } else if (kind === 'stab') {
    const sb = rows.filter((x) => String(x.bind).includes('SB')).length;
    const th = rows.map((x) => Number(x.thalf) || 0);
    add('结果行数', rows.length);
    add('强结合 SB', sb, '', 'green');
    add('最长半衰期', fmtNum(Math.max(...th)), 'h', 'purple');
    add('中位半衰期', fmtNum(th.sort((a, b) => a - b)[Math.floor(th.length / 2)] || 0), 'h');
  } else if (kind === 'pipeline') {
    add('蛋白数', summary.protein_count || 0);
    add('候选肽', summary.candidate_peptides || 0, '', 'amber');
    add('结合肽', summary.bound_peptides || 0, '', 'green');
    add('最终结果', summary.result_rows || rows.length, '', 'purple');
  } else if (kind === 'mutant') {
    const muts = r.mutations || [];
    add('突变位点', muts.length, '', 'purple');
    add('候选突变肽', r.candidate_peptides || 0);
    add('结果行数', rows.length);
    const sb = rows.filter((x) => String(x.bind_pan).includes('SB')).length;
    add('强结合 SB', sb, '', 'green');
  }

  box.hidden = false;
}

function renderTable() {
  const kind = state.resultKind;
  const cols = COLUMNS[kind] || COLUMNS.pan;
  const thead = $('resultThead');
  const tbody = $('resultTbody');

  // 表头
  thead.innerHTML = '';
  const tr = el('tr');
  cols.forEach((c) => {
    const th = el('th', c.cls === 'numeric' ? 'numeric' : '', c.label);
    if (c.w) th.style.width = c.w + 'px';
    th.onclick = () => {
      if (state.sortKey === c.key) state.sortDir *= -1;
      else { state.sortKey = c.key; state.sortDir = 1; }
      renderTable();
    };
    if (state.sortKey === c.key) th.textContent = c.label + (state.sortDir > 0 ? ' ↑' : ' ↓');
    tr.appendChild(th);
  });
  thead.appendChild(tr);

  // 过滤
  const q = $('tableSearch').value.trim().toUpperCase();
  const filt = $('tableFilter').value;

  let rows = state.resultRows.slice();

  if (q) {
    rows = rows.filter((r) =>
      cols.some((c) => String(r[c.key] ?? '').toUpperCase().includes(q))
    );
  }

  if (filt === 'sb') {
    rows = rows.filter((r) => String(r.bind || r.bind_pan || '').includes('SB'));
  } else if (filt === 'wb') {
    rows = rows.filter((r) => /SB|WB/.test(String(r.bind || r.bind_pan || '')));
  } else if (filt === 'binder') {
    rows = rows.filter((r) => /SB|WB/.test(String(r.bind || r.bind_pan || '')));
  }

  // 排序
  if (state.sortKey) {
    const k = state.sortKey;
    rows.sort((a, b) => {
      const av = a[k], bv = b[k];
      const an = Number(av), bn = Number(bv);
      if (Number.isFinite(an) && Number.isFinite(bn)) return (an - bn) * state.sortDir;
      return String(av ?? '').localeCompare(String(bv ?? '')) * state.sortDir;
    });
  }

  // 渲染（限制 3000 行，避免卡顿）
  const LIMIT = 3000;
  const shown = rows.slice(0, LIMIT);
  const frag = document.createDocumentFragment();

  shown.forEach((r, i) => {
    const bindStr = String(r.bind || r.bind_pan || '');
    const tr = el('tr');
    if (bindStr.includes('SB')) tr.className = 'sb';
    else if (bindStr.includes('WB')) tr.className = 'wb';

    cols.forEach((c) => {
      const td = el('td', c.cls || '');
      const v = r[c.key];
      if (c.render) {
        td.innerHTML = c.render(v, r);
      } else if (c.num) {
        td.textContent = fmtNum(v);
      } else if (c.strong) {
        td.textContent = v ?? '—';
        td.style.fontWeight = '600';
      } else {
        td.textContent = v ?? '—';
      }
      tr.appendChild(td);
    });
    frag.appendChild(tr);
  });

  tbody.innerHTML = '';
  tbody.appendChild(frag);

  $('rowCount').textContent =
    rows.length > LIMIT ? `${LIMIT} / ${rows.length} 行（已截断显示）` : `${rows.length} 行`;
}

// ─────────────────────────── 历史记录 ───────────────────────────

async function refreshHistoryBadge() {
  try {
    const d = await api('/api/history?limit=1');
    $('historyBadge').textContent = d.total ?? 0;
  } catch (e) { /* 忽略 */ }
}

async function openHistory() {
  state.historyOpen = true;
  $('historyDrawer').hidden = false;
  $('drawerBackdrop').hidden = false;
  const box = $('historyList');
  box.innerHTML = '<div class="hist-empty">加载中…</div>';
  try {
    const d = await api('/api/history?limit=100');
    box.innerHTML = '';
    if (!d.jobs.length) {
      box.innerHTML = '<div class="hist-empty">还没有历史记录<br>完成的预测任务会自动保存在这里</div>';
      return;
    }
    d.jobs.forEach((j) => {
      const it = el('div', 'hist-item');
      const top = el('div', 'hist-top');
      top.appendChild(el('div', 'hist-title', j.title));
      top.appendChild(el('span', 'pill ' + j.status, {
        done: '完成', failed: '失败', running: '运行中',
        queued: '排队', cancelled: '取消',
      }[j.status] || j.status));
      it.appendChild(top);

      const meta = el('div', 'hist-meta');
      const dt = new Date(j.created_at * 1000);
      meta.appendChild(el('span', '', dt.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      })));
      if (j.seconds) meta.appendChild(el('span', '', j.seconds.toFixed(1) + 's'));
      meta.appendChild(el('span', '', j.kind));
      it.appendChild(meta);

      it.onclick = () => loadHistoryJob(j.id);
      box.appendChild(it);
    });
  } catch (e) {
    box.innerHTML = `<div class="hist-empty">加载失败：${e.message}</div>`;
  }
}

async function loadHistoryJob(id) {
  try {
    const d = await api(`/api/jobs/${id}`);
    const job = d.job;
    closeHistory();

    if (job.status !== 'done') {
      toast('该任务未成功完成，无法查看结果', 'err');
      return;
    }
    // 切到对应模式
    const mode = job.kind === 'mutant' ? 'mutant' : job.kind;
    if (MODES[mode] && state.mode !== mode) setMode(mode);
    state.currentJob = job;
    setBusy(false);
    $('progressWrap').hidden = true;
    renderResult(job);
    toast('已载入历史任务');
  } catch (e) {
    toast('载入失败：' + e.message, 'err');
  }
}

function closeHistory() {
  state.historyOpen = false;
  $('historyDrawer').hidden = true;
  $('drawerBackdrop').hidden = true;
}

// ─────────────────────────── 导出 ───────────────────────────

function exportResult(fmt) {
  if (!state.currentJob) { toast('没有可导出的任务', 'err'); return; }
  const url = `/api/jobs/${state.currentJob.id}/export?format=${fmt}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(`正在下载 ${fmt.toUpperCase()} 文件…`);
}

// ─────────────────────────── 提示框 ───────────────────────────

function showAlert(msgs, kind) {
  const box = $('alertBox');
  box.hidden = false;
  box.className = 'alert ' + kind;
  box.innerHTML = '';
  if (msgs.length === 1) {
    box.textContent = msgs[0];
  } else {
    box.appendChild(document.createTextNode('请注意以下问题：'));
    const ul = el('ul');
    msgs.forEach((m) => ul.appendChild(el('li', '', m)));
    box.appendChild(ul);
  }
}

function hideAlert() {
  $('alertBox').hidden = true;
  $('alertBox').innerHTML = '';
}

// ─────────────────────────── 文件上传 ───────────────────────────

function setupFileUpload() {
  const tab = $('tabFile');
  const inp = $('fileInput');

  tab.onclick = () => inp.click();

  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const name = f.name.toLowerCase();

    if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv')) {
      // 表格文件：让用户在浏览器里解析
      await handleTableFile(f);
    } else {
      const text = await f.text();
      $('inputText').value = text;
      setInputType(text.trim().startsWith('>') ? 'fasta' : 'peptide');
      $('fileHint').hidden = false;
      $('fileHint').textContent = `已载入文件：${f.name}（${(f.size / 1024).toFixed(1)} KB）`;
      updateInputStats();
      toast('文件已载入');
    }
    inp.value = '';
  };
}

async function handleTableFile(f) {
  const name = f.name.toLowerCase();
  $('fileHint').hidden = false;

  if (name.endsWith('.csv') || name.endsWith('.tsv')) {
    const text = await f.text();
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
    if (!lines.length) { toast('文件为空', 'err'); return; }
    // 猜列：找像肽段的那一列
    const first = lines[0].split(/[,\t]/);
    let col = 0;
    const header = first.join(',').toLowerCase();
    if (/peptide|sequence|seq|肽|序列/.test(header)) {
      const idx = first.findIndex((h) => /peptide|sequence|seq|肽|序列/i.test(h));
      if (idx >= 0) col = idx;
    }
    const dataLines = /peptide|sequence|seq|肽|序列/i.test(header) ? lines.slice(1) : lines;
    const peps = dataLines
      .map((l) => (l.split(/[,\t]/)[col] || '').trim().toUpperCase())
      .filter((s) => /^[ACDEFGHIKLMNPQRSTVWY]+$/.test(s));

    if (!peps.length) { toast('没有从表格中识别出肽段序列', 'err'); return; }
    $('inputText').value = peps.join('\n');
    setInputType('peptide');
    $('fileHint').textContent = `从 ${f.name} 提取 ${peps.length} 条肽段（第 ${col + 1} 列）`;
    updateInputStats();
    toast(`已提取 ${peps.length} 条肽段`);
    return;
  }

  // xlsx：用浏览器端极简方案——提示转存为 CSV
  $('fileHint').textContent =
    'xlsx 需要先在 Excel 中「另存为 CSV UTF-8」，再上传 CSV。' +
    '也可以直接从 Excel 复制那一列单元格，粘贴到左侧输入框。';
  toast('xlsx 请先另存为 CSV，或直接粘贴单元格', 'err');
}

// ─────────────────────────── 事件绑定 ───────────────────────────

function bindEvents() {
  document.querySelectorAll('.nav-item').forEach((b) => {
    b.onclick = () => setMode(b.dataset.mode);
  });

  $('tabPeptide').onclick = () => { if (!MODES[state.mode].forceFasta) setInputType('peptide'); };
  $('tabFasta').onclick = () => setInputType('fasta');
  setupFileUpload();

  $('inputText').addEventListener('input', updateInputStats);

  $('btnSamplePan').onclick = () => {
    if (state.mode === 'chop' || state.mode === 'pipeline') {
      $('inputText').value = SAMPLES.fasta;
      setInputType('fasta');
    } else {
      $('inputText').value = SAMPLES.pep;
      setInputType('peptide');
    }
    updateInputStats();
  };

  $('btnClearInput').onclick = () => {
    $('inputText').value = '';
    $('fileHint').hidden = true;
    updateInputStats();
  };

  $('btnLoadMutantSample').onclick = () => {
    const ref = SAMPLES.mutantRef;
    // 制造一个真实突变：EGFR T790M（第 790 位 ACG -> ATG）
    if (ref.length > 789) {
      $('refSeq').value = ref;
      const alt = ref.slice(0, 789) + 'M' + ref.slice(790);
      $('altSeq').value = alt;
      toast('已填入 EGFR T790M 示例（第 790 位 T→M）');
    }
  };

  document.querySelectorAll('#mutLengths .len').forEach((b) => {
    b.onclick = () => {
      const L = Number(b.dataset.len);
      if (state.mutLengths.includes(L)) {
        if (state.mutLengths.length === 1) { toast('至少保留一个肽长', 'err'); return; }
        state.mutLengths = state.mutLengths.filter((x) => x !== L);
      } else {
        state.mutLengths = [...state.mutLengths, L].sort((a, b) => a - b);
      }
      document.querySelectorAll('#mutLengths .len').forEach((x) => {
        x.classList.toggle('active', state.mutLengths.includes(Number(x.dataset.len)));
      });
    };
  });

  $('btnRun').onclick = runJob;

  $('btnCancel').onclick = async () => {
    if (!state.currentJob) return;
    try {
      await api(`/api/jobs/${state.currentJob.id}/cancel`, { method: 'POST' });
      toast('正在取消…');
    } catch (e) {
      toast(e.message, 'err');
    }
  };

  $('btnExportCsv').onclick = () => exportResult('csv');
  $('btnExportXlsx').onclick = () => exportResult('xlsx');

  $('btnHistory').onclick = openHistory;
  $('btnCloseDrawer').onclick = closeHistory;
  $('drawerBackdrop').onclick = closeHistory;

  $('btnClearHistory').onclick = async () => {
    if (!confirm('确定清空全部历史记录？此操作不可恢复。')) return;
    try {
      const d = await api('/api/history/clear', { method: 'POST' });
      toast(`已清空 ${d.deleted} 条历史`);
      openHistory();
      refreshHistoryBadge();
    } catch (e) {
      toast(e.message, 'err');
    }
  };

  $('tableSearch').addEventListener('input', renderTable);
  $('tableFilter').addEventListener('change', renderTable);

  // 快捷键
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!state.busy) runJob();
    }
    if (e.key === 'Escape' && state.historyOpen) closeHistory();
  });
}

// ─────────────────────────── 启动 ───────────────────────────

async function init() {
  bindEvents();
  setupAlleleSearch();
  setMode('pan');
  renderAlleles();

  await checkHealth();
  await loadAlleles();
  refreshHistoryBadge();

  // 默认预选最常见的等位基因，降低上手门槛
  state.alleles = ['HLA-A02:01'];
  renderAlleles();

  setInterval(checkHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);
})();
