// 235 浏览器测试：对外接入（API 密钥）界面
const { chromium } = require('playwright-core');
const path = require('path');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = path.join(__dirname, '..', 'run', 'shots');

(async () => {
  const pass = [], fail = [];
  const ok = (n, c, d = '') => { (c ? pass : fail).push([n, d]); console.log(`  [${c ? 'PASS' : 'FAIL'}] ${n}${d ? '  [' + String(d).slice(0, 130) + ']' : ''}`); };

  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);

  console.log('\n【1】进入「数据库与工具」');
  await page.click('.nav-item[data-mode="resources"]');
  await page.waitForTimeout(900);
  ok('resourcesPanel 可见', await page.isVisible('#resourcesPanel'));

  console.log('\n【2】切到「对外接入」页签');
  await page.click('.res-tabs .chip[data-rtab="apikey"]');
  await page.waitForTimeout(700);
  ok('apikey 页签可见', await page.isVisible('#resPaneApikey'));
  ok('生成按钮存在', await page.isVisible('#btnCreateToken'));
  ok('接口速查含 /api/v1/tools', /\/api\/v1\/tools/.test(await page.textContent('#resPaneApikey')));

  console.log('\n【3】生成密钥');
  await page.fill('#tokenName', '浏览器测试密钥');
  await page.click('#btnCreateToken');
  await page.waitForTimeout(1200);
  const newBoxVisible = await page.isVisible('#tokenNewBox');
  const tokenVal = newBoxVisible ? (await page.textContent('#tokenNewValue')).trim() : '';
  ok('显示新密钥框', newBoxVisible);
  ok('密钥以 mhc_ 开头', tokenVal.startsWith('mhc_'), tokenVal.slice(0, 20));
  ok('密钥长度 36', tokenVal.length === 36, tokenVal.length);

  console.log('\n【4】密钥出现在列表');
  await page.waitForTimeout(600);
  const rows = await page.evaluate(() => {
    return [...document.querySelectorAll('#tokenTbody tr')].map(tr =>
      [...tr.querySelectorAll('td')].map(td => td.textContent.trim()));
  });
  ok('列表至少 1 行', rows.length >= 1, `${rows.length} 行`);
  const mine = rows.find(r => r[0] === '浏览器测试密钥');
  ok('列表含刚生成的密钥名', !!mine, mine ? mine.slice(0, 4).join(' | ') : '未找到');
  ok('列表显示前缀', !!mine && /^mhc_[0-9a-f]{8}…$/.test(mine[1]), mine ? mine[1] : '');
  ok('列表不显示明文密钥', !rows.some(r => r.some(c => c === tokenVal)));

  console.log('\n【5】用页面生成的密钥真实调用 API');
  const callRes = await page.evaluate(async (tok) => {
    const r = await fetch('/api/v1/predict/binding', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok },
      body: JSON.stringify({ peptides: ['SLYNTVATL'], alleles: ['HLA-A02:01'] }),
    });
    return { status: r.status, body: await r.json() };
  }, tokenVal);
  ok('页面内 fetch 调 v1 → 200', callRes.status === 200 && callRes.body.ok === true, `HTTP ${callRes.status}`);
  const s = (callRes.body.result || {}).summary || {};
  ok('返回真实预测结果', (s.count || 0) >= 1, `count=${s.count} SB=${s.strong_binders} aff=${(s.top_rows||[{}])[0].aff_nm}`);

  await page.screenshot({ path: path.join(SHOT, 'apikey_ui.png'), fullPage: true });

  console.log('\n【6】撤销密钥');
  page.on('dialog', d => d.accept());
  await page.evaluate(() => {
    const tr = [...document.querySelectorAll('#tokenTbody tr')].find(t => t.textContent.includes('浏览器测试密钥'));
    if (tr) [...tr.querySelectorAll('button')].find(b => b.textContent === '撤销')?.click();
  });
  await page.waitForTimeout(1500);
  const afterRevoke = await page.evaluate(async (tok) => {
    const r = await fetch('/api/v1/ping', { headers: { 'Authorization': 'Bearer ' + tok } });
    return r.status;
  }, tokenVal);
  ok('撤销后密钥失效（403）', afterRevoke === 403, `HTTP ${afterRevoke}`);

  console.log('\n【7】删除密钥');
  await page.evaluate(() => {
    const tr = [...document.querySelectorAll('#tokenTbody tr')].find(t => t.textContent.includes('浏览器测试密钥'));
    if (tr) [...tr.querySelectorAll('button')].find(b => b.textContent === '删除')?.click();
  });
  await page.waitForTimeout(1500);
  const gone = await page.evaluate(() => {
    return ![...document.querySelectorAll('#tokenTbody tr')].some(t => t.textContent.includes('浏览器测试密钥'));
  });
  ok('删除后列表已移除', gone);

  console.log('\n【8】控制台');
  // 第 6 步故意用已撤销的密钥请求，浏览器会打一条 403 资源错误，属预期
  const real = errors.filter(e => !/favicon|net::ERR_/.test(e) && !/403 \(Forbidden\)/.test(e));
  ok('无 JS 错误', real.length === 0, real.slice(0, 2).join(' | '));

  await browser.close();
  console.log(`\n===== 合计 PASS ${pass.length} / FAIL ${fail.length} =====`);
  if (fail.length) { fail.forEach(([n, d]) => console.log(`  ✘ ${n} — ${d}`)); process.exit(1); }
})();
