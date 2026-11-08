/**
 * dbg_maf.js — 诊断 TCGA MAF 上传为何没切到突变模式
 * 抓 /api/parse-file 的请求与响应、fileHint 文本、activeMode
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const OUT = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots');

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });

  page.on('console', (m) => console.log('[console]', m.type(), m.text().slice(0, 200)));
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  page.on('response', async (res) => {
    if (res.url().includes('/api/parse-file')) {
      let body = '';
      try { body = (await res.text()).slice(0, 600); } catch (e) { body = '<read fail>'; }
      console.log(`[net] ${res.status()} ${res.url()}`);
      console.log('[net body]', body);
    }
  });

  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.nav-item', { timeout: 20000 });

  fs.mkdirSync(OUT, { recursive: true });
  const mafPath = path.join(OUT, 'dbg_tcga.maf');
  fs.writeFileSync(mafPath, [
    'Hugo_Symbol\tChromosome\tStart_Position\tReference_Allele\tTumor_Seq_Allele2\tHGVSp_Short',
    'KRAS\tchr12\t25398284\tC\tA\tp.Gly12Asp',
    'TP53\tchr17\t7675088\tG\tA\tp.Arg273His',
  ].join('\n'), 'utf8');
  console.log('[file]', mafPath, fs.statSync(mafPath).size, 'B');

  await page.setInputFiles('#fileInput', mafPath);
  await page.waitForTimeout(2500);

  const hint = await page.locator('#fileHint').innerText().catch(() => '<none>');
  const hintCls = await page.locator('#fileHint').getAttribute('class').catch(() => '<none>');
  const active = await page.locator('.nav-item.active').getAttribute('data-mode');
  const badge = await page.locator('#pendingMutBadge').count();
  const stateJson = await page.evaluate(() => {
    const s = window.state || {};
    return {
      mode: s.mode,
      pendingMutations: s.pendingMutations ? s.pendingMutations.length : null,
      pendingMutSource: s.pendingMutSource || null,
      busy: s.busy,
      inputType: s.inputType,
    };
  });
  const hasState = await page.evaluate(() => typeof window.state !== 'undefined');

  console.log('--- 结果 ---');
  console.log('  fileHint  :', hint);
  console.log('  hint class:', hintCls);
  console.log('  activeMode:', active);
  console.log('  badgeCount:', badge);
  console.log('  window.state 可见:', hasState, JSON.stringify(stateJson));

  await page.screenshot({ path: path.join(OUT, 'dbg_maf.png'), fullPage: false });
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
