// ns_browser_test.js — 浏览器实机验证「非标准肽段处理」三种策略 + 标记 + 过滤器
// 运行: C:\AI\node.exe ns_browser_test.js
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOTS = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots_ns');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
fs.mkdirSync(SHOTS, { recursive: true });

let pass = 0, fail = 0;
const results = [];
function ok(name, cond, extra = '') {
  if (cond) { pass++; results.push(['PASS', name, extra]); console.log(`  PASS ${name} ${extra}`); }
  else { fail++; results.push(['FAIL', name, extra]); console.log(`  FAIL ${name} ${extra}`); }
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOTS, name + '.png'), fullPage: false });
}

async function waitJob(page, timeout = 90000) {
  // 抓 POST /api/jobs/* 的 job id
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const st = await page.evaluate(() => {
      const t = document.querySelector('#progressStage');
      return t ? t.textContent : '';
    }).catch(() => '');
    if (/完成|失败|取消/.test(st)) break;
    await page.waitForTimeout(300);
  }
  // 直接读结果表可见 + busy 解除
  await page.waitForFunction(() => {
    const b = document.querySelector('#btnRun');
    return b && !b.disabled;
  }, { timeout }).catch(() => {});
  await page.waitForTimeout(400);
}

async function setInput(page, text) {
  await page.fill('#inputText', text);
  await page.waitForTimeout(250);
}

async function pickNs(page, action) {
  await page.evaluate((a) => {
    const r = document.querySelector(`input[name="nsAction"][value="${a}"]`);
    if (r) { r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); }
  }, action);
  await page.waitForTimeout(150);
}

async function run(page) {
  const before = await page.evaluate(() => document.querySelector('#resultSub')?.textContent || '');
  await page.click('#btnRun');
  await waitJob(page);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));

  try {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.nav-item', { timeout: 20000 });
    console.log('== [1] 首页与非标准策略框 ==');
    ok('首页加载', await page.locator('.nav-item').count() >= 5);
    // 默认隐藏
    ok('nsPolicy 初始隐藏', await page.locator('#nsPolicy').isHidden());

    // 输入含 B/Z 的肽列表
    console.log('== [2] 含非标准残基输入 → 策略框出现 ==');
    await setInput(page, 'SLYNTVATL\nGILGFVFTL\nGILGFVFTZB\nAAAAAZAA');
    ok('nsPolicy 显示', !(await page.locator('#nsPolicy').isHidden()));
    const cnt = (await page.locator('#nsCount').textContent()) || '';
    ok('nsCount 提示数量', /2|非标准/.test(cnt), `text="${cnt.trim()}"`);
    ok('inputStats 标红', await page.evaluate(() => {
      const s = document.querySelector('#inputStats');
      return s && (s.style.color || '').includes('red') || (s.className || '').includes('warn');
    }) || /非标准/.test(await page.locator('#inputStats').textContent()));
    ok('三个 radio 齐全', await page.locator('input[name="nsAction"]').count() === 3);
    await shot(page, '01_ns_policy');

    // [3] mark 策略
    console.log('== [3] mark 标记并预测 ==');
    await pickNs(page, 'mark');
    await run(page);
    let rows = await page.locator('#resultTbody tr').count();
    ok('mark 有结果行', rows >= 3, `rows=${rows}`);
    const nsRows = await page.locator('#resultTbody tr.ns').count();
    ok('mark 有 tr.ns 高亮行', nsRows >= 2, `ns=${nsRows}`);
    const pepNs = await page.locator('#resultTbody .pep-ns').count();
    ok('mark 有 ⚠ 肽段角标', pepNs >= 2, `pep-ns=${pepNs}`);
    const sub = (await page.locator('#resultSub').textContent()) || '';
    ok('resultSub 带 ⚠ 提示', /非标准|⚠/.test(sub), `sub="${sub.trim()}"`);
    await shot(page, '02_mark');

    // [4] std 过滤器
    console.log('== [4] 隐藏非标准肽段过滤器 ==');
    await page.selectOption('#tableFilter', 'std');
    await page.waitForTimeout(300);
    const filtered = await page.locator('#resultTbody tr').count();
    ok('std 过滤后行数减少', filtered < rows, `before=${rows} after=${filtered}`);
    ok('std 过滤后无 ns 行', await page.locator('#resultTbody tr.ns').count() === 0);
    await page.selectOption('#tableFilter', 'all');
    await page.waitForTimeout(200);

    // [5] skip 策略
    console.log('== [5] skip 跳过 ==');
    await pickNs(page, 'skip');
    await run(page);
    const sk = await page.locator('#resultTbody tr.skipped').count();
    ok('skip 有灰色占位行', sk >= 2, `skipped=${sk}`);
    const reason = (await page.locator('#resultTbody tr.skipped').first().textContent()) || '';
    ok('占位行显示跳过原因', /非标准残基|已跳过/.test(reason), `text="${reason.trim().slice(0, 60)}"`);
    const sub2 = (await page.locator('#resultSub').textContent()) || '';
    ok('resultSub 显示已跳过 N 条', /已跳过/.test(sub2), `sub="${sub2.trim()}"`);
    await shot(page, '03_skip');

    // [6] remove 策略
    console.log('== [6] remove 删除 ==');
    await pickNs(page, 'remove');
    await run(page);
    const rows3 = await page.locator('#resultTbody tr').count();
    ok('remove 结果无占位行', await page.locator('#resultTbody tr.skipped').count() === 0);
    ok('remove 结果无 ns 高亮', await page.locator('#resultTbody tr.ns').count() === 0);
    const sub3 = (await page.locator('#resultSub').textContent()) || '';
    ok('resultSub 显示已移除 N 条', /已移除/.test(sub3), `sub="${sub3.trim()}"`);
    ok('remove 仍有正常结果', rows3 >= 2, `rows=${rows3}`);
    await shot(page, '04_remove');

    // [7] 导出仍可用
    console.log('== [7] 导出回归 ==');
    const dl = page.waitForEvent('download', { timeout: 15000 }).catch(() => null);
    await page.click('#btnExportCsv');
    const d = await dl;
    ok('CSV 导出触发', !!d, d ? `file=${d.suggestedFilename()}` : '');

    // [8] 控制台
    ok('控制台无 JS 错误', errors.length === 0, errors.slice(0, 2).join(' | '));
  } catch (e) {
    fail++;
    results.push(['FAIL', 'EXCEPTION', String(e)]);
    console.log('EXCEPTION', e);
    await shot(page, '99_exception').catch(() => {});
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify({ pass, fail, results }, null, 2));
    console.log(`\n=== NS 浏览器测试: PASS ${pass} / FAIL ${fail} ===`);
    process.exit(fail ? 1 : 0);
  }
})();
