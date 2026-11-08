/**
 * neo_e2e.js — 真实使用场景：新抗原一键筛选（v1.3.0 核心新功能）
 *
 * 模拟一位研究者：
 *   1. 打开工作台 → 切到「新抗原一键筛选」
 *   2. 填入 KRAS G12V（胰腺癌最常见突变之一）
 *   3. 预览蛋白与候选肽
 *   4. 选 HLA-A*11:01（KRAS 12 位点的正确 HLA）
 *   5. 肽长选 9 和 10
 *   6. 提交 → 等完成 → 看步骤卡片/KPI/表格
 *   7. 按结合筛选 → 导出 CSV
 *   8. 从 GDC 导入突变（真实 TCGA-PAAD 数据）
 *   9. 检查历史记录
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const OUT = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots');
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function ok(name, cond, detail = '') {
  results.push({ name, pass: !!cond, detail: String(detail).slice(0, 160) });
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  [' + String(detail).slice(0, 120) + ']' : ''}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 950 },
    acceptDownloads: true,
  });
  const page = await ctx.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('favicon')) errors.push('console: ' + m.text());
  });

  // 抓提交返回的 job id
  let lastJobId = null;
  page.on('response', async (res) => {
    const u = res.url();
    if (/\/api\/jobs\//.test(u) && res.request().method() === 'POST' && !/cancel/.test(u)) {
      try {
        const d = await res.json();
        if (d.job && d.job.id) lastJobId = d.job.id;
      } catch (e) { /* ignore */ }
    }
  });

  const shot = async (n) => { await page.screenshot({ path: path.join(OUT, 'neo_' + n + '.png') }); };

  console.log('\n【1】打开工作台');
  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.nav-item', { timeout: 25000 });
  const navCount = await page.locator('.nav-item').count();
  ok('侧栏 8 个模式', navCount === 8, navCount + ' 个');
  const neoNav = page.locator('.nav-item[data-mode="neoantigen"]');
  ok('存在「新抗原一键筛选」入口', (await neoNav.count()) === 1);

  console.log('\n【2】切到新抗原模式');
  await neoNav.click();
  await page.waitForTimeout(700);
  ok('标题正确', (await page.locator('#modeTitle').innerText()).includes('新抗原'),
    await page.locator('#modeTitle').innerText());
  ok('突变输入框可见', await page.locator('#neoMutations').isVisible());
  ok('主输入框隐藏（新抗原模式不用主输入框）',
    !(await page.locator('.field').first().isVisible().catch(() => false)) ||
    (await page.locator('#neoBlock').isVisible()));

  console.log('\n【3】填入 KRAS G12V 并预览');
  await page.fill('#neoMutations', 'KRAS G12V');
  await page.waitForTimeout(300);
  const stats = await page.locator('#neoStats').innerText();
  ok('统计显示已输入突变', /1|突变/.test(stats), stats.slice(0, 60));

  await page.click('#btnNeoPreview');
  await page.waitForTimeout(6000);
  const previewVisible = await page.locator('#neoPreview').isVisible();
  const previewTxt = previewVisible ? await page.locator('#neoPreview').innerText() : '';
  ok('预览区展开', previewVisible);
  ok('预览显示 KRAS 与登录号', /KRAS/.test(previewTxt) && /P01116/.test(previewTxt), previewTxt.slice(0, 100));
  ok('预览显示候选肽数', /候选|肽/.test(previewTxt), previewTxt.slice(0, 100));
  await shot('01_preview');

  console.log('\n【4】选 HLA-A*11:01');
  // 先清空默认的 A02:01
  const tags = await page.locator('#alleleSelected .allele-tag').count();
  for (let i = 0; i < tags; i++) {
    const btn = page.locator('#alleleSelected .allele-tag button').first();
    if (await btn.count()) await btn.click().catch(() => {});
    await page.waitForTimeout(150);
  }
  await page.click('#alleleSearch');
  await page.fill('#alleleSearch', 'A11:01');
  await page.waitForTimeout(900);
  const opt = page.locator('#alleleDropdown .allele-option').first();
  const optTxt = await opt.innerText().catch(() => '');
  ok('搜到 A11:01', /A\*?11:01/.test(optTxt), optTxt);
  await opt.click();
  await page.waitForTimeout(400);
  const chosen = await page.locator('#alleleSelected').innerText();
  ok('已选 A11:01', /11:01/.test(chosen), chosen.replace(/\s+/g, ' ').slice(0, 60));

  console.log('\n【5】肽长选 9 和 10');
  // 参数面板里找「肽长」
  const setLen = async (want) => {
    const done = await page.evaluate((want) => {
      const rows = [...document.querySelectorAll('#paramsPanel .param-row')];
      const row = rows.find((r) => (r.querySelector('.param-label strong') || {}).textContent === '肽长');
      if (!row) return 'no-row';
      const btns = [...row.querySelectorAll('.len')];
      let changed = 0;
      for (const b of btns) {
        const len = Number(b.textContent.trim());
        const on = b.classList.contains('active');
        const should = want.includes(len);
        if (should !== on) { b.click(); changed++; }
      }
      return changed + '/' + btns.length;
    }, want);
    return done;
  };
  const lenRes = await setLen([9, 10]);
  await page.waitForTimeout(400);
  const lenState = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('#paramsPanel .param-row')];
    const row = rows.find((r) => (r.querySelector('.param-label strong') || {}).textContent === '肽长');
    return row ? [...row.querySelectorAll('.len.active')].map((b) => Number(b.textContent.trim())) : null;
  });
  ok('肽长设置为 9,10', JSON.stringify(lenState) === '[9,10]', JSON.stringify(lenState) + ' (改动 ' + lenRes + ')');

  console.log('\n【6】提交并等待完成');
  lastJobId = null;
  await page.click('#btnRun');
  // 任务可能 0.5 秒就完成，运行态检查要立刻做
  let sawBusy = false;
  for (let i = 0; i < 20; i++) {
    const b = await page.locator('#btnRunText').innerText().catch(() => '');
    if (/运行中/.test(b)) { sawBusy = true; break; }
    if (lastJobId) break;
    await sleep(50);
  }
  ok('提交后进入运行态（或极快完成）', sawBusy || !!lastJobId, sawBusy ? '运行中' : ('已捕获 job ' + lastJobId));

  // 等后端任务完成
  let job = null;
  for (let i = 0; i < 120; i++) {
    await sleep(1000);
    if (!lastJobId) continue;
    const r = await ctx.request.get(`${URL}/api/jobs/${lastJobId}`);
    if (!r.ok()) continue;
    const d = await r.json();
    const j = d.job || d;
    if (['done', 'failed', 'cancelled'].includes(j.status)) { job = j; break; }
  }
  ok('任务完成', job && job.status === 'done', job ? `${job.status} ${job.seconds}s` : 'timeout');
  if (!job || job.status !== 'done') {
    console.log('  错误:', JSON.stringify(job && job.error).slice(0, 300));
  }

  await page.waitForTimeout(1500);

  console.log('\n【7】检查结果渲染');
  const title = await page.locator('#resultTitle').innerText().catch(() => '');
  ok('结果标题为新抗原', /新抗原/.test(title), title);
  const sub = await page.locator('#resultSub').innerText().catch(() => '');
  ok('副标题显示行数与耗时', /行结果/.test(sub) && /秒/.test(sub), sub);

  const steps = await page.locator('#stepsBox').innerText().catch(() => '');
  ok('五步步骤卡片齐全',
    ['UniProt', 'NetChop', '突变肽生成', 'NetMHCpan', 'NetMHCstabpan'].every((s) => steps.includes(s)),
    steps.replace(/\s+/g, ' ').slice(0, 200));

  const kpi = await page.locator('#kpiBox').innerText().catch(() => '');
  ok('KPI 含突变位点/候选/结合', /突变|候选|结合/.test(kpi), kpi.replace(/\s+/g, ' ').slice(0, 120));

  const thead = await page.locator('#resultThead').innerText().catch(() => '');
  ok('表头含突变/突变肽/野生型肽/Δ排名',
    ['突变', '突变肽', '野生型', 'Δ'].every((c) => thead.includes(c)),
    thead.replace(/\s+/g, ' ').slice(0, 200));

  const rowCount = await page.locator('#resultTbody tr').count();
  ok('结果表有行', rowCount > 0, rowCount + ' 行');
  const firstRow = rowCount ? await page.locator('#resultTbody tr').first().innerText() : '';
  ok('首行是 KRAS G12V', /G12V/.test(firstRow), firstRow.replace(/\s+/g, ' ').slice(0, 140));
  ok('首行有结合标签', /SB|WB/.test(firstRow), firstRow.replace(/\s+/g, ' ').slice(0, 140));
  await shot('02_result');

  console.log('\n【8】筛选结合肽');
  await page.selectOption('#tableFilter', 'binder');
  await page.waitForTimeout(600);
  const binderRows = await page.locator('#resultTbody tr').count();
  ok('筛选结合肽后行数减少', binderRows < rowCount, `${rowCount} → ${binderRows}`);
  ok('结合肽不为 0（KRAS G12V × A11:01 应有 SB）', binderRows >= 1, binderRows + ' 行');
  await page.selectOption('#tableFilter', 'all');
  await page.waitForTimeout(400);

  console.log('\n【9】导出 CSV');
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 30000 }).catch(() => null),
    page.click('#btnExportCsv'),
  ]);
  if (dl) {
    const p = path.join(OUT, 'neo_export.csv');
    await dl.saveAs(p);
    const sz = fs.statSync(p).size;
    const txt = fs.readFileSync(p, 'utf8');
    ok('CSV 下载成功', sz > 200, sz + ' B, ' + dl.suggestedFilename());
    ok('CSV 有 BOM', txt.charCodeAt(0) === 0xfeff);
    ok('CSV 含基因与肽列', /基因/.test(txt) && /突变肽/.test(txt), txt.split('\n')[0].slice(0, 100));
  } else {
    ok('CSV 下载成功', false, '未触发下载');
  }

  console.log('\n【10】从 GDC 导入真实突变');
  await page.click('#btnNeoFromGdc');
  await page.waitForTimeout(5000);
  const mutVal = await page.locator('#neoMutations').inputValue();
  ok('GDC 导入后突变框有内容', mutVal.trim().length > 0, mutVal.split('\n').slice(0, 3).join(' | '));
  ok('导入格式为「基因 突变」', /^[A-Z0-9]+\s+[A-Z]\d+[A-Z]/m.test(mutVal), mutVal.split('\n')[0]);
  await shot('03_gdc_import');

  console.log('\n【11】历史记录');
  await page.click('#btnHistory');
  await page.waitForTimeout(1200);
  const histTxt = await page.locator('#historyList').innerText().catch(() => '');
  ok('历史里有「新抗原筛选」', /新抗原/.test(histTxt), histTxt.replace(/\s+/g, ' ').slice(0, 120));
  await page.click('#btnCloseDrawer').catch(() => {});
  await page.waitForTimeout(500);

  console.log('\n【12】控制台');
  ok('无 JS 错误', errors.length === 0, errors.slice(0, 2).join(' | '));

  fs.writeFileSync(
    path.join(OUT, 'neo_e2e_report.json'),
    JSON.stringify({ url: URL, pass: results.filter((r) => r.pass).length, fail: results.filter((r) => !r.pass).length, results }, null, 2),
    'utf8'
  );

  const pass = results.filter((r) => r.pass).length;
  const fail = results.length - pass;
  console.log('\n' + '='.repeat(60));
  console.log(`  新抗原真实场景 E2E：${pass}/${results.length} 通过`);
  if (fail) {
    console.log('  失败项：');
    results.filter((r) => !r.pass).forEach((r) => console.log('   ✘', r.name, '—', r.detail));
  }
  console.log('='.repeat(60));

  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
