const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  // 1) 直接用 context.request 打 /api/jobs/<id>
  const r1 = await ctx.request.get(`${BASE}/api/jobs/da3d5808c2584bc2`);
  console.log('GET /api/jobs/<id> ->', r1.status(), r1.headers()['content-type']);
  const t1 = await r1.text();
  console.log('  前 80:', JSON.stringify(t1.slice(0, 80)));

  // 2) POST 一个 stab 任务，看响应
  const r2 = await ctx.request.post(`${BASE}/api/jobs/stab`, {
    data: { input: 'SLYNTVATL\nGILGFVFTL', input_mode: 'peptide', alleles: ['HLA-A02:01'], with_ia: true },
  });
  console.log('\nPOST /api/jobs/stab ->', r2.status(), r2.headers()['content-type']);
  const t2 = await r2.text();
  console.log('  前 120:', JSON.stringify(t2.slice(0, 120)));

  // 3) 页面内 fetch 同一接口
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  const inPage = await page.evaluate(async () => {
    const res = await fetch('/api/jobs/da3d5808c2584bc2');
    const txt = await res.text();
    return { status: res.status, ct: res.headers.get('content-type'), head: txt.slice(0, 80) };
  });
  console.log('\n页面内 fetch ->', JSON.stringify(inPage));

  await browser.close();
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
