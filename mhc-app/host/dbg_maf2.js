/**
 * dbg_maf2.js — 复现 browser_test 的 13a→13c 顺序：先传 IEDB CSV，再传 MAF
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
  page.on('console', (m) => {
    const t = m.text();
    if (!t.includes('Password field')) console.log('[console]', m.type(), t.slice(0, 250));
  });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message, '\n', (e.stack || '').split('\n').slice(0, 4).join('\n')));

  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.nav-item', { timeout: 20000 });
  fs.mkdirSync(OUT, { recursive: true });

  // 13a IEDB CSV
  const csvPath = path.join(OUT, 'dbg_iedb.csv');
  fs.writeFileSync(csvPath, [
    'allele,peptide,percentile_rank',
    'HLA-A*02:01,SLYNTVATL,0.08',
    'HLA-A*02:01,GILGFVFTL,0.19',
    'HLA-A*24:02,MLLSVPLLL,0.14',
  ].join('\n'), 'utf8');
  await page.setInputFiles('#fileInput', csvPath);
  await page.waitForTimeout(1200);
  console.log('[13a] hint =', (await page.locator('#fileHint').innerText().catch(() => '')).slice(0, 120));
  console.log('[13a] mode =', await page.locator('.nav-item.active').getAttribute('data-mode'));

  // 全部带入（若出现）
  const btn = page.locator('#presetRow button');
  if (await btn.count()) { await btn.first().click(); await page.waitForTimeout(800); }
  console.log('[13b] 已选等位基因 =', await page.locator('#alleleSelected .allele-tag').count());

  // 13c MAF
  const mafPath = path.join(OUT, 'dbg_tcga2.maf');
  fs.writeFileSync(mafPath, [
    'Hugo_Symbol\tChromosome\tStart_Position\tReference_Allele\tTumor_Seq_Allele2\tHGVSp_Short',
    'KRAS\tchr12\t25398284\tC\tA\tp.Gly12Asp',
    'TP53\tchr17\t7675088\tG\tA\tp.Arg273His',
  ].join('\n'), 'utf8');
  await page.setInputFiles('#fileInput', mafPath);
  await page.waitForTimeout(2500);
  console.log('[13c] hint =', (await page.locator('#fileHint').innerText().catch(() => '')).slice(0, 200));
  console.log('[13c] mode =', await page.locator('.nav-item.active').getAttribute('data-mode'));
  console.log('[13c] badge =', await page.locator('#pendingMutBadge').count());
  const toastTxt = await page.locator('#toastStack .toast').allInnerTexts().catch(() => []);
  console.log('[13c] toasts =', JSON.stringify(toastTxt));

  await page.screenshot({ path: path.join(OUT, 'dbg_maf2.png') });
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
