// 调试：资源模式 → evaluate 点击 nav-item 后的状态
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

  // 尝试 evaluate 点击
  await p.evaluate(() => {
    const items = document.querySelectorAll('.nav-item');
    for (const btn of items) if (btn.dataset.mode === 'neoantigen') btn.click();
  });
  await p.waitForTimeout(600);
  console.log('active nav:', await p.evaluate(() => document.querySelector('.nav-item.active')?.dataset.mode));
  console.log('neoBlock hidden:', await p.evaluate(() => document.getElementById('neoBlock')?.hidden));
  console.log('neoBlock visible:', await p.locator('#neoBlock').isVisible().catch(() => 'ERR'));
  console.log('busy state:', await p.evaluate(() => window.state ? window.state.busy : 'no state'));
  console.log('panel-input display:', await p.evaluate(() => document.querySelector('.panel-input')?.style.display));
  await p.screenshot({ path: 'dbg_res2neo.png' });
  await b.close();
})();
