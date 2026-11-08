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
  resources: {
    title: '数据库与在线工具',
    desc: '设计书所需的 GDC/TCGA 突变检索、IEDB 云端预测，以及其余数据库与在线工具入口。',
    needAllele: false,
    inputLabel: '资源中心',
    placeholder: '',
    acceptFasta: false,
    isResource: true,
  },
  agent: {
    title: '智能助手',
    desc: '用自然语言指挥工作台：自动查 UniProt/ClinVar/PubMed 数据库、批量跑预测、汇总成报告。',
    needAllele: false,
    isAgent: true,
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
  pendingMutations: null,
  pendingMutSource: '',
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

  // 资源中心：整块替换掉「输入 + 结果」两栏
  const isResource = !!cfg.isResource;
  $('resourcesPanel').hidden = !isResource;
  document.querySelector('.panel-input').style.display = isResource ? 'none' : '';
  document.querySelector('.panel-result').style.display = isResource ? 'none' : '';
  document.querySelector('.layout').classList.toggle('res-layout', isResource);
  if (isResource) {
    loadResourceCatalog();
    return;
  }

  // 智能助手：同样整块替换
  const isAgent = !!cfg.isAgent;
  $('agentPanel').hidden = !isAgent;
  document.querySelector('.panel-input').style.display = isAgent ? 'none' : '';
  document.querySelector('.panel-result').style.display = isAgent ? 'none' : '';
  document.querySelector('.layout').classList.toggle('agent-layout', isAgent);
  if (isAgent) {
    agentEnsureSession();
    agentLoadCfg();
    return;
  }

  // 突变模式：换掉主输入区
  const isMutant = mode === 'mutant';
  const refField = document.querySelector('.field');
  if (isMutant && state.pendingMutations) {
    // 文件驱动的突变筛选：主输入区当「参考蛋白 FASTA」用
    refField.style.display = '';
    $('mutantBlock').hidden = true;
    $('inputText').placeholder = '粘贴参考蛋白 FASTA（蛋白名对应突变基因，如 >KRAS）';
    const label = refField.querySelector('.field-head label');
    if (label) label.textContent = '参考蛋白 FASTA';
  } else if (isMutant) {
    // 传统双序列对比
    refField.style.display = 'none';
    $('mutantBlock').hidden = false;
    const label = refField.querySelector('.field-head label');
    if (label) label.textContent = '输入序列';
  } else {
    refField.style.display = '';
    $('mutantBlock').hidden = true;
    const label = refField.querySelector('.field-head label');
    if (label) label.textContent = '输入序列';
  }

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

  // 突变模式下 pendingMutations 提示徽标
  let badge = $('pendingMutBadge');
  if (isMutant && state.pendingMutations) {
    if (!badge) {
      badge = el('span', 'pending-mut-badge');
      badge.id = 'pendingMutBadge';
      const head = document.querySelector('.field .field-head');
      if (head) head.insertBefore(badge, head.querySelector('.field-actions'));
    }
    badge.textContent = `已载入 ${state.pendingMutations.length} 个突变（${state.pendingMutSource || '文件'}）`;
    badge.hidden = false;
  } else if (badge) {
    badge.hidden = true;
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
  if (state.mode === 'mutant' && state.pendingMutations) {
    ta.placeholder = '粘贴参考蛋白 FASTA（蛋白名对应突变基因，如 >KRAS）';
  } else {
    ta.placeholder = t === 'fasta'
      ? '粘贴蛋白序列，必须以 > 开头：\n>my_protein\nMLLSVPLLLGLLGAAACSSNCGSS'
      : MODES[state.mode].placeholder;
  }
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
  if (!s.count) {
    box.textContent = '尚未输入';
    updateNsPolicy(s);
    return;
  }

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
  updateNsPolicy(s);
}

/** 读取用户选择的非标准肽段处理策略：mark / skip / remove */
function getNsAction() {
  const r = document.querySelector('input[name="nsAction"]:checked');
  return r ? r.value : 'mark';
}

/** 检测到非标准残基时显示策略选择器；突变模式检测参考/突变序列 */
function updateNsPolicy(s) {
  const policy = $('nsPolicy');
  if (!policy) return;

  let nsCount = 0;
  let bad = s.bad || [];

  if (state.mode === 'mutant') {
    // 突变模式：非标准字符来自参考/突变两条序列
    const ref = $('refSeq').value.toUpperCase().replace(/[^A-Z]/g, '');
    const alt = $('altSeq').value.toUpperCase().replace(/[^A-Z]/g, '');
    bad = [...new Set((ref + alt).replace(/[ACDEFGHIKLMNPQRSTVWY]/g, '').split(''))].filter(Boolean);
    nsCount = [ref, alt].filter((x) => x && /[^ACDEFGHIKLMNPQRSTVWY]/.test(x)).length;
  } else {
    nsCount = (s.seqs || []).filter((x) => /[^ACDEFGHIKLMNPQRSTVWY]/.test(x)).length;
  }

  if (bad.length) {
    policy.hidden = false;
    $('nsCount').textContent =
      `${nsCount} 条序列含非标准字符 ${bad.join('')} · 当前策略：${
        { mark: '标记并预测', skip: '跳过', remove: '删除' }[getNsAction()]
      }`;
  } else {
    policy.hidden = true;
    $('nsCount').textContent = '';
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
  } else if (state.pendingMutations) {
    // 文件驱动的突变筛选：主输入框 = 参考蛋白 FASTA
    const fasta = $('inputText').value.trim();
    if (!fasta || !fasta.startsWith('>')) {
      toast('请先在输入框粘贴参考蛋白 FASTA（以 > 开头，蛋白名对应突变基因）', 'err');
      showAlert(['来自文件的突变列表已就绪，但缺少参考蛋白序列。请在输入框粘贴对应基因的蛋白 FASTA，例如：\n>KRAS\nMTEYKLVVVGAVGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV...'], 'error');
      return;
    }
    payload.input = fasta;
    payload.mutations = state.pendingMutations;
    payload.peptide_lengths = state.mutLengths;
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

  // 非标准肽段处理策略（mark/skip/remove），对所有模式生效
  payload.nonstandard_action = getNsAction();

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
          nonstandard_action: payload.nonstandard_action,
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
  // 非标准肽段处理提示
  let nsNote = '';
  if (r.nonstandard_skipped) nsNote = ` · 已跳过 ${r.nonstandard_skipped} 条非标准肽段`;
  else if (r.nonstandard_removed) nsNote = ` · 已移除 ${r.nonstandard_removed} 条非标准肽段`;
  else if (r.nonstandard_proteins_skipped) {
    nsNote = ` · 已跳过 ${r.nonstandard_proteins_skipped.length} 条含非标准残基的蛋白`;
  } else if (r.nonstandard_action === 'mark') {
    const nsRows = state.resultRows.filter((x) => x.nonstandard && !x.skipped).length;
    if (nsRows) nsNote = ` · ${nsRows} 行带 ⚠ 非标准标记`;
  }
  $('resultSub').textContent =
    `${n} 行结果 · 耗时 ${job.seconds ? job.seconds.toFixed(1) : '?'} 秒` +
    (r.candidates ? ` · 候选肽 ${r.candidates}` : '') +
    nsNote;

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
  } else if (filt === 'std') {
    // 隐藏非标准肽段：mark 模式带 ⚠ 的行 + skip 模式的灰色占位行
    rows = rows.filter((r) => !r.nonstandard && !r.skipped);
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
    if (r.skipped) tr.className = 'skipped';
    else if (bindStr.includes('SB')) tr.className = 'sb';
    else if (bindStr.includes('WB')) tr.className = 'wb';
    if (r.nonstandard && !r.skipped) tr.classList.add('ns');

    cols.forEach((c) => {
      const td = el('td', c.cls || '');
      let v = r[c.key];
      // skip 占位行的数值列显示跳过原因而不是 —
      if (r.skipped && (c.num || c.key === 'bind' || c.key === 'bind_pan')) {
        td.textContent = r.skipped_reason || '已跳过';
        td.colSpan = 1;
        tr.appendChild(td);
        return;
      }
      if (c.render) {
        td.innerHTML = c.render(v, r);
      } else if (c.key === 'peptide' && r.nonstandard) {
        // 非标准肽段：⚠ 角标
        const wrap = el('span', 'pep-ns', String(v ?? '—'));
        wrap.title = '含非标准残基，工具内部当作 X 处理，数值仅供参考';
        td.appendChild(wrap);
        td.style.fontWeight = '600';
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

// ─────────────────────────── 文件上传（服务端通用解析） ───────────────────────────

const FILE_ACCEPT = '.txt,.fa,.fasta,.faa,.csv,.tsv,.xlsx,.xls,.vcf,.maf,.tsv.maf,.gz';

function setupFileUpload() {
  const tab = $('tabFile');
  const inp = $('fileInput');

  tab.onclick = () => inp.click();

  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    await handleAnyFile(f);
    inp.value = '';
  };
}

async function handleAnyFile(f) {
  const hint = $('fileHint');
  hint.hidden = false;
  hint.textContent = `正在解析 ${f.name}（${(f.size / 1024).toFixed(1)} KB）…`;
  hint.className = 'file-hint';

  try {
    let payload;
    if (/\.(xlsx|xls)$/i.test(f.name) || f.size > 2 * 1024 * 1024 ||
        /\.(vcf|maf)(\.gz)?$/i.test(f.name) || /\.gz$/i.test(f.name)) {
      // 二进制 / 大文件 / 压缩格式：整体 base64 送服务端
      const buf = await f.arrayBuffer();
      let bytes = new Uint8Array(buf);
      if (/\.gz$/i.test(f.name)) {
        try {
          const ds = new DecompressionStream('gzip');
          const stream = new Blob([bytes]).stream().pipeThrough(ds);
          bytes = new Uint8Array(await new Response(stream).arrayBuffer());
        } catch (e) {
          throw new Error('gzip 解压失败：' + e.message);
        }
      }
      // 分块转二进制字符串：String.fromCharCode 一次最多吃 ~65535 个参数，
      // 且 chunkify 返回「块的数组」，必须逐块拼接而不是整体展开
      let bin = '';
      for (const chunk of chunkify(bytes, 32768)) {
        bin += String.fromCharCode.apply(null, chunk);
      }
      payload = {
        filename: f.name,
        content_b64: btoa(bin),
      };
    } else {
      payload = { filename: f.name, text: await f.text() };
    }

    const r = await api('/api/parse-file', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    applyParseResult(f.name, r);
  } catch (e) {
    hint.className = 'file-hint err';
    hint.textContent = `解析失败：${e.message}`;
    toast('文件解析失败：' + e.message, 'err');
  }
}

function chunkify(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.subarray(i, i + size));
  return out;
}

/** 把 /api/parse-file 结果落到 UI */
function applyParseResult(fname, r) {
  const hint = $('fileHint');
  hint.hidden = false;
  hint.className = 'file-hint';

  const fmtLabel = r.format || '未知格式';
  const notes = r.notes || [];

  // ── 情形 1：蛋白 / 肽段 ──
  if (r.kind === 'proteins' || r.kind === 'peptides') {
    const text = r.kind === 'proteins'
      ? (r.proteins_text || '')
      : (r.peptides || []).join('\n');
    $('inputText').value = text;
    setInputType(r.kind === 'proteins' ? 'fasta' : 'peptide');

    const n = r.kind === 'proteins' ? (text.match(/^>/gm) || []).length : r.peptide_count;
    let msg = `${fname} → 识别为 ${fmtLabel}，${n} 条${r.kind === 'proteins' ? '蛋白' : '肽段'}已填入输入框`;
    if (r.alleles && r.alleles.length) msg += `；发现 ${r.alleles.length} 个等位基因`;
    hint.textContent = msg + (notes.length ? '：' + notes.join('；') : '');
    hint.className = 'file-hint';

    // 等位基因列 → 一键带入
    if (r.alleles && r.alleles.length) {
      offerAlleles(r.alleles);
    }
    updateInputStats();
    toast(`已识别 ${fmtLabel}，${n} 条${r.kind === 'proteins' ? '蛋白' : '肽段'}`);
    return;
  }

  // ── 情形 2：变体 / 突变列表 → 引导进突变肽筛选 ──
  if (r.kind === 'variants' || r.kind === 'mutations') {
    const nMut = (r.mutations || []).length;
    const nVar = r.variant_count || (r.variants || []).length;
    if (!nMut && !nVar) {
      hint.className = 'file-hint err';
      hint.textContent = `${fname} → ${fmtLabel}，但 ${notes.join('；')}`;
      toast('文件已识别但无可用的蛋白级突变', 'err');
      return;
    }

    // 存到状态，切到 mutant 模式
    state.pendingMutations = r.mutations || [];
    state.pendingMutSource = `${fname}（${fmtLabel}）`;
    setMode('mutant');

    const mutBlock = $('mutantBlock');
    // 显示参考 FASTA 输入区（复用主输入框区域更顺：把主输入框当参考 FASTA 用）
    const refField = document.querySelector('.field');
    refField.style.display = '';
    $('inputText').placeholder =
      '粘贴参考蛋白 FASTA（蛋白名对应突变基因，如 >KRAS）';
    const label = refField.querySelector('.field-head label');
    if (label) label.textContent = '参考蛋白 FASTA';

    hint.textContent =
      `${fname} → 识别为 ${fmtLabel}：${nVar} 个变异，其中 ${nMut} 个带蛋白级注释已就绪。` +
      '请在上方输入框粘贴对应的参考蛋白 FASTA（蛋白名与基因对应），然后点「开始预测」。' +
      (notes.length ? ' ' + notes.join(' ') : '');
    hint.className = 'file-hint';
    toast(`已识别 ${fmtLabel}：${nMut} 个蛋白级突变，请提供参考 FASTA`);
    return;
  }

  hint.className = 'file-hint err';
  hint.textContent = `${fname}：${notes.join('；') || '无法识别文件结构'}`;
  toast('无法识别该文件', 'err');
}

/** 提供把文件里解析出的等位基因一键带入选择 */
function offerAlleles(alleles) {
  const box = $('presetRow');
  // 避免重复注入
  if ($('fileAlleleOffer')) return;
  const wrap = el('div', 'file-allele-offer');
  wrap.id = 'fileAlleleOffer';
  const span = el('span', '', `文件中发现 ${alleles.length} 个等位基因：`);
  wrap.appendChild(span);
  const btn = el('button', 'btn btn-ghost btn-sm', '全部带入');
  btn.onclick = () => {
    alleles.forEach((a) => {
      if (!state.alleles.includes(a)) state.alleles.push(a);
    });
    renderAlleles();
    wrap.remove();
    toast(`已带入 ${alleles.length} 个等位基因`);
  };
  wrap.appendChild(btn);
  const skip = el('button', 'btn btn-ghost btn-sm', '忽略');
  skip.onclick = () => wrap.remove();
  wrap.appendChild(skip);
  box.appendChild(wrap);
}

// ─────────────────────────── 资源中心 ───────────────────────────

const resState = {
  catalog: null,
  gdcRows: [],
  iedbRows: [],
  loading: false,
};

async function loadResourceCatalog(force = false) {
  if (resState.catalog && !force) { renderResourceCatalog(); return; }
  try {
    const d = await api('/api/resources');
    resState.catalog = d;
    renderResourceCatalog();
  } catch (e) {
    toast('读取资源清单失败：' + e.message, 'err');
  }
}

function renderResourceCatalog() {
  const c = resState.catalog;
  if (!c) return;

  // 项目下拉
  const sel = $('gdcProject');
  if (sel.options.length === 0) {
    (c.gdc_projects || []).forEach((p) => {
      const o = el('option', '', p.name);
      o.value = p.id;
      sel.appendChild(o);
    });
  }

  // 驱动基因快捷芯片
  const chips = $('gdcGeneChips');
  if (chips.children.length === 0) {
    (c.paad_drivers || []).forEach((g) => {
      const b = el('button', 'chip', g);
      b.onclick = () => { $('gdcGene').value = g; searchGdc(); };
      chips.appendChild(b);
    });
  }

  // 数据库卡片
  const dbGrid = $('resDbGrid');
  dbGrid.innerHTML = '';
  (c.databases || []).forEach((d) => dbGrid.appendChild(resourceCard(d, 'db')));

  // 工具卡片
  const toolGrid = $('resToolGrid');
  toolGrid.innerHTML = '';
  (c.tools || []).forEach((t) => toolGrid.appendChild(resourceCard(t, 'tool')));
}

function resourceCard(item, kind) {
  const card = el('div', 'res-card');

  const top = el('div', 'res-card-top');
  const nameBox = el('div');
  nameBox.appendChild(el('div', 'res-card-name', item.name));
  if (item.full) nameBox.appendChild(el('div', 'res-card-full', item.full));
  top.appendChild(nameBox);

  let badgeTxt = '';
  let badgeCls = 'off';
  if (kind === 'db') {
    if (item.builtin) { badgeTxt = '内嵌可检索'; badgeCls = 'embed'; }
    else { badgeTxt = item.api || '外链'; badgeCls = 'ok'; }
  } else {
    badgeTxt = item.status || '';
    if (/在线可用/.test(badgeTxt)) badgeCls = 'ok';
    else if (/403|不可达|变更/.test(badgeTxt)) badgeCls = 'warn';
    else badgeCls = 'off';
  }
  if (badgeTxt) top.appendChild(el('span', 'res-badge ' + badgeCls, badgeTxt));
  card.appendChild(top);

  if (item.stage) card.appendChild(el('div', 'res-card-full', '环节：' + item.stage));
  card.appendChild(el('div', 'res-card-desc', item.desc || ''));

  const tags = el('div', 'res-card-tags');
  (item.tags || []).forEach((t) => tags.appendChild(el('span', 'res-tag', t)));
  if (item.local_alt) tags.appendChild(el('span', 'res-tag', '本地替代：' + item.local_alt));
  card.appendChild(tags);

  const foot = el('div', 'res-card-foot');
  const a = el('a', 'btn btn-ghost btn-sm', '打开 ↗');
  a.href = item.url;
  a.target = '_blank';
  a.rel = 'noopener';
  foot.appendChild(a);
  if (item.builtin && item.id === 'gdc-paad') {
    const b = el('button', 'btn btn-ghost btn-sm', '在此检索突变');
    b.onclick = () => { switchResTab('gdc'); $('gdcProject').value = 'TCGA-PAAD'; };
    foot.appendChild(b);
  }
  if (item.builtin && item.id === 'iedb-tools') {
    const b = el('button', 'btn btn-ghost btn-sm', '在此调用预测');
    b.onclick = () => switchResTab('iedb');
    foot.appendChild(b);
  }
  card.appendChild(foot);
  return card;
}

function switchResTab(name) {
  document.querySelectorAll('.res-tabs .chip').forEach((b) => {
    b.classList.toggle('active', b.dataset.rtab === name);
  });
  $('resPaneGdc').hidden = name !== 'gdc';
  $('resPaneIedb').hidden = name !== 'iedb';
  $('resPaneCatalog').hidden = name !== 'catalog';
}

async function searchGdc() {
  const project = $('gdcProject').value || 'TCGA-PAAD';
  const gene = $('gdcGene').value.trim();
  const chrom = $('gdcChrom').value.trim();
  const mutType = $('gdcMutType').value;
  const meta = $('gdcMeta');
  meta.textContent = '查询中…';
  $('btnGdcSearch').disabled = true;
  try {
    const d = await api('/api/gdc/mutations', {
      method: 'POST',
      body: JSON.stringify({ project, gene, chromosome: chrom, mutation_type: mutType, size: 500 }),
    });
    resState.gdcRows = d.rows || [];
    renderGdcTable();
    const bits = [`<strong>${d.total}</strong> 条突变（返回 ${d.returned} 条）`];
    if (gene) bits.push(`基因 <strong>${gene.toUpperCase()}</strong>`);
    if (chrom) bits.push(`染色体 <strong>${chrom}</strong>`);
    bits.push(`队列 <strong>${project}</strong>`);
    meta.innerHTML = bits.join(' · ');
    if (!resState.gdcRows.length) {
      meta.innerHTML += ' — 没有匹配的突变，换基因或去掉过滤条件再试';
    }
  } catch (e) {
    meta.textContent = '查询失败：' + e.message;
    toast(e.message, 'err');
  } finally {
    $('btnGdcSearch').disabled = false;
  }
}

const GDC_COLS = [
  { key: 'gene', label: '基因', w: 80 },
  { key: 'aa_change', label: '氨基酸改变', w: 100 },
  { key: 'consequence_type', label: '变异类型', w: 130 },
  { key: 'dna_change', label: '基因组改变', w: 190 },
  { key: 'chromosome', label: '染色体', w: 70 },
  { key: 'start', label: '位置', w: 100, cls: 'numeric' },
  { key: 'mutation_subtype', label: '突变亚型', w: 150 },
  { key: 'transcript_id', label: '转录本', w: 130 },
];

function renderGdcTable() {
  const thead = $('gdcThead');
  const tbody = $('gdcTbody');
  const table = $('gdcTable');
  thead.innerHTML = '';
  tbody.innerHTML = '';
  if (!resState.gdcRows.length) { table.hidden = true; return; }
  table.hidden = false;

  const tr = el('tr');
  GDC_COLS.forEach((c) => {
    const th = el('th', c.cls === 'numeric' ? 'numeric' : '', c.label);
    if (c.w) th.style.width = c.w + 'px';
    tr.appendChild(th);
  });
  thead.appendChild(tr);

  resState.gdcRows.forEach((r) => {
    const row = el('tr');
    GDC_COLS.forEach((c) => {
      let v = r[c.key];
      if (v === null || v === undefined || v === '') v = '—';
      const td = el('td', c.cls === 'numeric' ? 'numeric' : '', String(v));
      if (c.key === 'aa_change' && v !== '—') td.style.fontWeight = '600';
      if (c.key === 'gene' && v !== '—') td.style.color = 'var(--primary)';
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
}

async function runIedb() {
  const cls = $('iedbClass').value;
  const method = $('iedbMethod').value;
  const length = Number($('iedbLength').value) || (cls === 'I' ? 9 : 15);
  const alleleRaw = $('iedbAlleles').value.trim();
  const input = $('iedbInput').value;
  const meta = $('iedbMeta');

  if (!alleleRaw) { toast('请填写至少一个 HLA 等位基因', 'err'); return; }
  if (!input.trim()) { toast('请粘贴肽段，每行一条', 'err'); return; }

  const alleles = alleleRaw.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
  meta.textContent = '正在调用 IEDB（可能需要 10–60 秒）…';
  $('btnIedbRun').disabled = true;
  $('iedbSpinner').hidden = false;
  $('iedbRunText').textContent = '预测中…';

  try {
    const d = await api('/api/iedb/predict', {
      method: 'POST',
      body: JSON.stringify({ mhc_class: cls, method, input, alleles, length }),
    });
    resState.iedbRows = d.rows || [];
    renderIedbTable();
    meta.innerHTML = `IEDB <strong>${d.method}</strong> · ${d.peptides} 条肽 × ${d.alleles.length} 个等位基因 · <strong>${d.count}</strong> 行结果`;
    if (d.errors && d.errors.length) {
      meta.innerHTML += ' · 部分失败：' + d.errors.join('; ');
    }
  } catch (e) {
    meta.textContent = 'IEDB 调用失败：' + e.message;
    toast(e.message, 'err');
  } finally {
    $('btnIedbRun').disabled = false;
    $('iedbSpinner').hidden = true;
    $('iedbRunText').textContent = '调用 IEDB 预测';
  }
}

function renderIedbTable() {
  const thead = $('iedbThead');
  const tbody = $('iedbTbody');
  const table = $('iedbTable');
  thead.innerHTML = '';
  tbody.innerHTML = '';
  if (!resState.iedbRows.length) { table.hidden = true; return; }
  table.hidden = false;

  // IEDB 返回列名随方法不同，取首行 keys
  const keys = Object.keys(resState.iedbRows[0]).filter((k) => !k.startsWith('_'));
  const tr = el('tr');
  keys.forEach((k) => tr.appendChild(el('th', '', k)));
  thead.appendChild(tr);

  resState.iedbRows.forEach((r) => {
    const row = el('tr');
    keys.forEach((k) => {
      let v = r[k];
      if (v === null || v === undefined || v === '') v = '—';
      const td = el('td', /rank|ic50|score/i.test(k) ? 'numeric' : '', String(v));
      if (k === 'percentile_rank' || k === 'rank') {
        const n = parseFloat(v);
        if (!isNaN(n)) {
          const s = el('span', 'tag ' + (n < 0.5 ? 'sb' : n < 2 ? 'wb' : 'none'), String(v));
          td.textContent = '';
          td.appendChild(s);
        }
      }
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
}

function bindResourceEvents() {
  document.querySelectorAll('.res-tabs .chip').forEach((b) => {
    b.onclick = () => switchResTab(b.dataset.rtab);
  });
  $('btnGdcSearch').onclick = searchGdc;
  $('gdcGene').addEventListener('keydown', (e) => { if (e.key === 'Enter') searchGdc(); });
  $('btnIedbRun').onclick = runIedb;
  $('btnIedbSample').onclick = () => {
    $('iedbInput').value = SAMPLES.pep;
    updateIedbStats();
  };
  $('iedbInput').addEventListener('input', updateIedbStats);
  $('iedbClass').addEventListener('change', () => {
    const cls = $('iedbClass').value;
    $('iedbLength').value = cls === 'I' ? 9 : 15;
    fillIedbMethods(cls);
  });
}

function fillIedbMethods(cls) {
  const c = resState.catalog;
  if (!c) return;
  const list = (c.iedb_methods || {})[cls === 'I' ? 'mhci' : 'mhcii'] || [];
  const sel = $('iedbMethod');
  sel.innerHTML = '';
  list.forEach(([val, label]) => {
    const o = el('option', '', label);
    o.value = val;
    sel.appendChild(o);
  });
}

function updateIedbStats() {
  const raw = $('iedbInput').value;
  const lines = raw.split('\n').map((s) => s.trim()).filter(Boolean);
  const stat = $('iedbStats');
  if (!lines.length) { stat.textContent = '尚未输入'; return; }
  const lens = [...new Set(lines.map((s) => s.length))].sort((a, b) => a - b);
  stat.textContent = `${lines.length} 条肽 · 长度 ${lens.join('/')}`;
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
      updateNsPolicy(analyzeInput());
      toast('已填入 EGFR T790M 示例（第 790 位 T→M）');
    }
  };

  // 突变序列输入实时联动非标准策略框
  ['refSeq', 'altSeq'].forEach((id) => {
    $(id).addEventListener('input', () => updateNsPolicy(analyzeInput()));
  });

  // 切换处理策略时刷新计数提示
  document.querySelectorAll('input[name="nsAction"]').forEach((r) => {
    r.addEventListener('change', () => updateNsPolicy(analyzeInput()));
  });

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

  bindResourceEvents();

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

// ==================== 智能助手（Agent）====================
let agentSessionId = null;
let agentStreamAbort = null;

async function agentEnsureSession() {
  if (agentSessionId) return;
  try {
    const r = await fetch('/api/agent/sessions', { method: 'POST' });
    const d = await r.json();
    agentSessionId = d.session && d.session.id;
  } catch (e) {
    toast('创建助手会话失败：' + e.message, 'err');
  }
}

async function agentLoadCfg() {
  try {
    const r = await fetch('/api/agent/config');
    const d = await r.json();
    const c = d.config || {};
    $('agentBaseUrl').value = c.base_url || '';
    $('agentModel').value = c.model || '';
    $('agentCfgStatus').textContent = c.has_key ? `已配置 (${c.key_hint || 'key'})` : '未配置 API Key';
    if (c.base_url) $('agentConfigBox').hidden = true;  // 已有配置则不展开
  } catch (e) { /* ignore */ }
}

function agentOpenConfig() { $('agentConfigBox').hidden = false; }
function agentCloseConfig() {
  $('agentConfigBox').hidden = true;
  agentLoadCfg();
}

async function agentSaveCfg() {
  const base_url = $('agentBaseUrl').value.trim();
  const api_key = $('agentApiKey').value.trim();
  const model = $('agentModel').value.trim();
  if (!base_url || !model) { toast('请填写 Base URL 与模型名', 'err'); return; }
  const payload = { base_url, model };
  if (api_key) payload.api_key = api_key;
  try {
    const r = await fetch('/api/agent/config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || '保存失败');
    $('agentApiKey').value = '';
    agentCloseConfig();
    toast('模型配置已保存');
  } catch (e) { toast('保存失败：' + e.message, 'err'); }
}

function agentAppendMsg(role, text, kind) {
  const chat = $('agentChat');
  const wrap = document.createElement('div');
  wrap.className = 'agent-msg ' + (role === 'user' ? 'user' : 'assistant') + (kind ? ' ' + kind : '');
  if (kind === 'tool') {
    wrap.classList.add('agent-tool');
    const pre = document.createElement('pre');
    pre.textContent = text;
    wrap.appendChild(pre);
  } else {
    wrap.innerHTML = role === 'assistant' && text ? md2html(text) : escHtml(text);
  }
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

// 极简 Markdown 渲染（标题/列表/表格/代码）
function md2html(md) {
  let h = escHtml(md);
  h = h.replace(/^### (.*)$/gm, '<h4>$1</h4>');
  h = h.replace(/^## (.*)$/gm, '<h3>$1</h3>');
  h = h.replace(/^# (.*)$/gm, '<h2>$1</h2>');
  h = h.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
  h = h.replace(/`([^`]*)`/g, '<code>$1</code>');
  // 表格
  h = h.replace(/\|(.*)\|\s*$/gm, function (m, row) {
    const cells = row.split('|').map(s => s.trim());
    return '<tr>' + cells.map(c => '<td>' + c + '</td>').join('') + '</tr>';
  });
  // 列表
  const li = h.match(/[^\n]*\n/g);
  h = h.replace(/^- (.*)$/gm, '<li>$1</li>');
  h = h.replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>');
  h = h.split('\n').map(l => /^<tr>|<h[234]>|<ul>|<li>|<\/ul>/.test(l) || !l.trim() ? l : '<p>' + l + '</p>').join('\n');
  return h;
}

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function agentShowStatus(msg) { $('agentStatus').textContent = msg; }
function agentHideStatus() { $('agentStatus').textContent = ''; }

async function agentSend() {
  const input = $('agentInput');
  const text = input.value.trim();
  if (!text || agentStreamAbort) return;
  if (!agentSessionId) await agentEnsureSession();
  input.value = '';
  const chat = $('agentChat');
  const wel = $('agentWelcome');
  if (wel) wel.hidden = true;

  agentAppendMsg('user', text);
  agentShowStatus('助手思考中…');
  const btn = $('btnAgentSend');
  btn.disabled = true;

  // 流式读取
  const ctrl = new AbortController();
  agentStreamAbort = ctrl;

  let acc = '';
  const msgs = [];
  try {
    const resp = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: agentSessionId, message: text }),
      signal: ctrl.signal,
    });
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}));
      throw new Error(j.error || ('HTTP ' + resp.status));
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let assistantWrap = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      // 按 \n\n 切 SSE
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        const line = chunk.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') continue;
        let ev;
        try { ev = JSON.parse(data); } catch { continue; }
        if (ev.type === 'tool_start') {
          msgs.push({ type: 'tool', name: ev.name });
          agentAppendMsg('tool', '🔧 调用 ' + ev.name + (ev.args ? '：' + JSON.stringify(ev.args).slice(0, 200) : ''), 'tool');
          agentShowStatus('调用 ' + ev.name + '…');
        } else if (ev.type === 'tool_result') {
          msgs.push({ type: 'tool_result', name: ev.name, ok: ev.ok });
          agentAppendMsg('tool', (ev.ok ? '✅ ' : '⚠️ ') + ev.name + ' 完成' + (ev.preview ? '：' + ev.preview : ''), 'tool');
        } else if (ev.type === 'final') {
          if (!assistantWrap) assistantWrap = agentAppendMsg('assistant', '', '');
          assistantWrap.innerHTML = md2html(ev.message || '');
          assistantWrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else if (ev.type === 'error') {
          agentAppendMsg('assistant', '⚠️ ' + ev.message, '');
        }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') agentAppendMsg('assistant', '⚠️ ' + e.message, '');
  } finally {
    agentStreamAbort = null;
    btn.disabled = false;
    agentHideStatus();
    chat.scrollTop = chat.scrollHeight;
  }
}

function agentAbort() {
  if (agentStreamAbort) { agentStreamAbort.abort(); agentStreamAbort = null; }
}

// 绑定 agent 事件
document.addEventListener('DOMContentLoaded', function agentBind() {
  if (!document.getElementById('btnAgentSend')) return;
  document.getElementById('btnAgentSend').onclick = agentSend;
  document.getElementById('btnAgentConfig').onclick = agentOpenConfig;
  document.getElementById('btnAgentCfgCancel').onclick = agentCloseConfig;
  document.getElementById('btnAgentSaveCfg').onclick = agentSaveCfg;
  const ai = document.getElementById('agentInput');
  ai.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); agentSend(); }
  });
});

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

  // 资源中心：预加载清单并填充 IEDB 方法列表
  await loadResourceCatalog();
  fillIedbMethods('I');
  updateIedbStats();

  setInterval(checkHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);
})();
