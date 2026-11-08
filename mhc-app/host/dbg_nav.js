const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
(async () => {
  const b = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const p = await (await b.newContext()).newPage();
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.nav-item');
  const info = await p.evaluate(() => {
    const els = [...document.querySelectorAll('.nav-item')];
    return els.map((e) => ({
      mode: e.dataset.mode || '(none)',
      text: (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40),
      parent: e.parentElement ? e.parentElement.tagName + '.' + e.parentElement.className : '?',
      visible: !!(e.offsetWidth || e.offsetHeight),
    }));
  });
  console.log('count =', info.length);
  info.forEach((x, i) => console.log(`  ${i}: mode=${x.mode} | ${x.text} | parent=${x.parent} | visible=${x.visible}`));
  await b.close();
})();
