// 调试：neoFromGdc 为何没切模式——检查 resState.gdcRows 与 missense 过滤
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const p = await (await b.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
  p.on('pageerror', (e) => console.log('PAGEERROR', e.message));

  await p.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
  await p.locator('.nav-item[data-mode="resources"]').click();
  await p.waitForTimeout(800);
  await p.locator('#gdcGeneChips .chip', { hasText: 'KRAS' }).first().click();
  await p.waitForFunction(
    () => { const m = document.getElementById('gdcMeta'); return m && /9\s*条突变/.test(m.textContent); },
    null, { timeout: 90000 },
  );

  const info = await p.evaluate(() => {
    const rows = window.__resRows || [];
    return { rowsLen: rows.length };
  });
  console.log('via helper:', JSON.stringify(info));

  // 直接读 resState（不在 window 上，试全局作用域）
  const diag = await p.evaluate(() => {
    // resState 是 IIFE 内 const，无法直接访问；用 __mhc 暴露一个探针
    return typeof window.__mhcResState !== 'undefined' ? window.__mhcResState : 'not exposed';
  });
  console.log('resState probe:', JSON.stringify(diag));

  // 表格行内容
  const firstRows = await p.locator('#gdcTbody tr').allTextContents();
  console.log('table first rows:');
  firstRows.slice(0, 3).forEach((r) => console.log('  ', r.replace(/\s+/g, ' ').slice(0, 110)));

  // 手动模拟过滤逻辑，看看 aa_change 的真实值
  const aaVals = await p.locator('#gdcTbody tr td:nth-child(2)').allTextContents();
  const csqVals = await p.locator('#gdcTbody tr td:nth-child(3)').allTextContents();
  console.log('aa_change col:', aaVals.join(','));
  console.log('csq col:', csqVals.join(','));

  await b.close();
})();
