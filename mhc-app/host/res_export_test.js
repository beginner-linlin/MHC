// 浏览器端验证「数据库检索结果导出」按钮：GDC 与 IEDB 各导 CSV + xlsx。
// 跑法：C:\AI\node.exe res_export_test.js
const { chromium } = require('playwright-core');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = process.env.MHC_SHOT_DIR || require('path').join(__dirname, '..', 'run', 'shots');
const fs = require('fs');
const path = require('path');

const results = [];
function ok(name, cond, extra) {
  results.push({ name, pass: !!cond, extra: extra === undefined ? '' : String(extra) });
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (extra !== undefined ? ' = ' + extra : ''));
}

(async () => {
  fs.mkdirSync(SHOT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });

  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.nav-item');
  await page.click('.nav-item[data-mode="resources"]');
  await page.waitForSelector('#resourcesPanel:not([hidden])');

  // ---------- GDC ----------
  await page.click('.res-tabs .chip[data-rtab="gdc"]');
  await page.waitForSelector('#resPaneGdc:not([hidden])');
  ok('GDC 导出按钮初始隐藏', await page.locator('#gdcActions').isHidden());

  await page.selectOption('#gdcProject', 'TCGA-PAAD');
  await page.fill('#gdcGene', 'KRAS');
  await page.click('#btnGdcSearch');
  await page.waitForFunction(() => {
    const m = document.getElementById('gdcMeta');
    return m && m.textContent && !m.textContent.includes('查询中');
  }, null, { timeout: 90000 });
  const gdcMeta = await page.textContent('#gdcMeta');
  ok('GDC 检索有结果', /条突变/.test(gdcMeta), gdcMeta.slice(0, 60));
  ok('GDC 检索后导出按钮可见', await page.locator('#gdcActions').isVisible());

  // GDC CSV 下载
  let [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.click('#btnGdcExportCsv'),
  ]);
  const csvPath = path.join(SHOT, 'gdc_export.csv');
  await dl.saveAs(csvPath);
  const csvBuf = fs.readFileSync(csvPath);
  ok('GDC CSV 下载成功', csvBuf.length > 200, csvBuf.length + 'B');
  ok('GDC CSV 文件名', /\.csv$/.test(dl.suggestedFilename()), dl.suggestedFilename());
  ok('GDC CSV 带 BOM', csvBuf[0] === 0xef && csvBuf[1] === 0xbb && csvBuf[2] === 0xbf);
  const csvHead = csvBuf.toString('utf8').split(/\r?\n/)[0];
  ok('GDC CSV 表头中文', csvHead.includes('基因') && csvHead.includes('氨基酸改变'), csvHead.slice(0, 50));

  // GDC xlsx 下载
  [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.click('#btnGdcExportXlsx'),
  ]);
  const xlsxPath = path.join(SHOT, 'gdc_export.xlsx');
  await dl.saveAs(xlsxPath);
  const xlsxBuf = fs.readFileSync(xlsxPath);
  ok('GDC xlsx 下载成功', xlsxBuf.length > 3000, xlsxBuf.length + 'B');
  ok('GDC xlsx 魔数', xlsxBuf[0] === 0x50 && xlsxBuf[1] === 0x4b);

  // ---------- IEDB ----------
  await page.click('.res-tabs .chip[data-rtab="iedb"]');
  await page.waitForSelector('#resPaneIedb:not([hidden])');
  ok('IEDB 导出按钮初始隐藏', await page.locator('#iedbActions').isHidden());

  await page.selectOption('#iedbClass', 'I');
  await page.fill('#iedbAlleles', 'HLA-A*02:01');
  await page.fill('#iedbInput', 'SLYNTVATL\nGILGFVFTL');
  await page.click('#btnIedbRun');
  await page.waitForFunction(() => {
    const m = document.getElementById('iedbMeta');
    return m && m.textContent && !m.textContent.includes('正在调用');
  }, null, { timeout: 180000 });
  const iedbMeta = await page.textContent('#iedbMeta');
  ok('IEDB 预测有结果', /行结果/.test(iedbMeta), iedbMeta.slice(0, 60));
  ok('IEDB 预测后导出按钮可见', await page.locator('#iedbActions').isVisible());

  [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.click('#btnIedbExportCsv'),
  ]);
  const icsv = path.join(SHOT, 'iedb_export.csv');
  await dl.saveAs(icsv);
  const icsvBuf = fs.readFileSync(icsv);
  ok('IEDB CSV 下载成功', icsvBuf.length > 100, icsvBuf.length + 'B');
  const icsvHead = icsvBuf.toString('utf8').split(/\r?\n/)[0];
  ok('IEDB CSV 表头中文', icsvHead.includes('HLA') && icsvHead.includes('肽段'), icsvHead.slice(0, 60));

  [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.click('#btnIedbExportXlsx'),
  ]);
  const ixlsx = path.join(SHOT, 'iedb_export.xlsx');
  await dl.saveAs(ixlsx);
  const ixlsxBuf = fs.readFileSync(ixlsx);
  ok('IEDB xlsx 下载成功', ixlsxBuf.length > 3000, ixlsxBuf.length + 'B');
  ok('IEDB xlsx 魔数', ixlsxBuf[0] === 0x50 && ixlsxBuf[1] === 0x4b);

  // 截图
  await page.click('.res-tabs .chip[data-rtab="gdc"]');
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOT, 'res_export_gdc.png'), fullPage: false });
  await page.click('.res-tabs .chip[data-rtab="iedb"]');
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOT, 'res_export_iedb.png'), fullPage: false });

  ok('无 JS 错误', errors.length === 0, errors.slice(0, 3).join(' | '));

  const pass = results.filter((r) => r.pass).length;
  console.log(`\n===== ${pass}/${results.length} PASS =====`);
  const fails = results.filter((r) => !r.pass);
  if (fails.length) {
    console.log('失败项：');
    fails.forEach((f) => console.log('  - ' + f.name + ' = ' + f.extra));
  }
  fs.writeFileSync(path.join(SHOT, 'res_export_report.json'), JSON.stringify(results, null, 2));
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})().catch((e) => {
  console.error('FATAL', e);
  process.exit(2);
});
