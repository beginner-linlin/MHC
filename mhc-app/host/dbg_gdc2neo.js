// 调试：window.__mhc.neoFromGdc 调用后到底发生什么
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const p = await (await b.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
  p.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('CONSOLE', m.type(), m.text().slice(0, 120)); });

  await p.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
  await p.locator('.nav-item[data-mode="resources"]').click();
  await p.waitForTimeout(800);

  // 查 KRAS
  await p.locator('#gdcGeneChips .chip', { hasText: 'KRAS' }).first().click();
  await p.waitForFunction(
    () => { const m = document.getElementById('gdcMeta'); return m && /9\s*条突变/.test(m.textContent); },
    null, { timeout: 90000 },
  );
  console.log('gdcMeta OK');

  console.log('__mhc exists:', await p.evaluate(() => !!window.__mhc));
  console.log('__mhc keys:', await p.evaluate(() => window.__mhc ? Object.keys(window.__mhc) : []));

  const r = await p.evaluate(() => {
    try {
      const rows = (window.__mhc && window.__mhc._rows) || 'no helper';
      window.__mhc.neoFromGdc();
      return { called: true };
    } catch (e) { return { called: false, err: e.message }; }
  });
  console.log('neoFromGdc result:', JSON.stringify(r));
  await p.waitForTimeout(800);
  console.log('active nav:', await p.evaluate(() => document.querySelector('.nav-item.active')?.dataset.mode));
  console.log('neoBlock hidden attr:', await p.evaluate(() => String(document.getElementById('neoBlock')?.hidden)));
  console.log('neoMutations value:', await p.evaluate(() => document.getElementById('neoMutations')?.value));
  console.log('neoBlock visible:', await p.locator('#neoBlock').isVisible().catch(() => 'ERR'));
  await p.screenshot({ path: 'dbg_gdc2neo.png' });
  await b.close();
})();
