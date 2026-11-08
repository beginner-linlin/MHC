// 调试：新抗原模式下 HLA 预设点击为何没选中
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const p = await (await b.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
  p.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  p.on('console', (m) => { if (m.type() === 'error') console.log('CONSOLE', m.text()); });

  await p.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
  await p.locator('.nav-item[data-mode="neoantigen"]').click();
  await p.waitForTimeout(800);

  console.log('presetRow html:', (await p.locator('#presetRow').innerHTML()).slice(0, 300));
  console.log('preset btn count:', await p.locator('#presetRow .preset-btn').count());
  console.log('alleleSelected before:', JSON.stringify(await p.locator('#alleleSelected').innerHTML()));

  await p.locator('#presetRow .preset-btn').first().click();
  await p.waitForTimeout(500);
  console.log('alleleSelected after:', JSON.stringify(await p.locator('#alleleSelected').innerHTML()));
  console.log('alleleCount:', await p.locator('#alleleCount').textContent());
  console.log('state.alleles:', await p.evaluate(() => window.state ? window.state.alleles : 'no window.state'));

  await p.screenshot({ path: 'C:/Users/86156/Desktop/大创/软件/整合/mhc-workbench/mhc-app/run/shots/dbg_allele.png' });
  await b.close();
})();
