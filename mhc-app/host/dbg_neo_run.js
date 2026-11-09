const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const page = await browser.newPage();
  const logs = [];
  page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
  page.on('request', (r) => {
    if (r.url().includes('/api/')) logs.push(`[req] ${r.method()} ${r.url().replace('http://127.0.0.1:8080', '')}`);
  });
  page.on('response', (r) => {
    if (r.url().includes('/api/jobs')) logs.push(`[res] ${r.status()} ${r.url().replace('http://127.0.0.1:8080', '')}`);
  });

  await page.goto('http://127.0.0.1:8080/', { waitUntil: 'networkidle' });
  await page.locator('.nav-item[data-mode="neoantigen"]').click();
  await page.waitForTimeout(500);

  // 状态检查
  const st = await page.evaluate(() => {
    const w = window.__mhc;
    return {
      hasMhc: !!w,
      mode: w && w.state ? w.state.mode : null,
      params: w && w.state ? JSON.stringify(w.state.params) : null,
      alleles: w && w.state ? JSON.stringify(w.state.alleles) : null,
      busy: w && w.state ? w.state.busy : null,
      paramsPanelRows: document.querySelectorAll('#paramsPanel .param-row').length,
      neoBlockHidden: document.getElementById('neoBlock').hidden,
    };
  });
  console.log('状态:', JSON.stringify(st, null, 2));

  await page.locator('#neoMutations').fill('KRAS G12D');
  await page.waitForTimeout(300);

  logs.length = 0;
  await page.locator('#btnRun').click();
  await page.waitForTimeout(6000);

  const after = await page.evaluate(() => {
    const w = window.__mhc;
    return {
      busy: w && w.state ? w.state.busy : null,
      currentJob: w && w.state && w.state.currentJob ? w.state.currentJob.id : null,
      alertHidden: document.getElementById('alertBox').hidden,
      alertText: document.getElementById('alertBox').textContent,
      toasts: [...document.querySelectorAll('#toastStack .toast')].map((t) => t.textContent),
      resultTitle: document.getElementById('resultTitle').textContent,
      resultSub: document.getElementById('resultSub').textContent,
    };
  });
  console.log('\n点击后:', JSON.stringify(after, null, 2));
  console.log('\n日志:');
  logs.forEach((l) => console.log('  ' + l));

  await browser.close();
})();
