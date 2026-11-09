// 227 浏览器验证（修正选择器 .agent-msg）：智能助手工具调用过程是否可见
const { chromium } = require('playwright-core');
const path = require('path');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT_DIR = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots');

(async () => {
  const pass = [], fail = [];
  const ok = (n, c, d = '') => { (c ? pass : fail).push([n, d]); console.log(`  [${c ? 'PASS' : 'FAIL'}] ${n}${d ? '  [' + String(d).slice(0, 140) + ']' : ''}`); };

  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);

  console.log('\n【1】切到智能助手');
  await page.click('.nav-item[data-mode="agent"]');
  await page.waitForTimeout(900);
  ok('agentPanel 可见', await page.isVisible('#agentPanel'));

  console.log('\n【2】发送会触发工具的消息');
  await page.fill('#agentInput', '用 NetMHCpan 预测肽段 SLYNTVATL 对 HLA-A02:01 的结合亲和力');
  await page.click('#btnAgentSend');

  // 轮询直到出现「非工具」的 assistant 最终回答（最多 150 秒）
  let finalText = '';
  for (let i = 0; i < 300; i++) {
    await page.waitForTimeout(500);
    finalText = await page.evaluate(() => {
      const n = [...document.querySelectorAll('#agentChat .agent-msg.assistant')]
        .filter(x => !x.classList.contains('tool'));   // 排除工具气泡
      return n.map(x => x.textContent).join('\n').trim();
    });
    if (finalText.length > 20) break;
  }
  ok('收到最终回答', finalText.length > 20, finalText.slice(0, 100));

  console.log('\n【3】工具调用气泡（真实类名 .agent-msg）');
  const bubbles = await page.evaluate(() => {
    return [...document.querySelectorAll('#agentChat .agent-msg')].map(n => ({
      cls: n.className,
      text: n.textContent.trim().slice(0, 140),
    }));
  });
  bubbles.forEach(b => console.log(`      ${b.cls} → ${b.text}`));

  const toolBubbles = bubbles.filter(b => /tool/.test(b.cls));
  ok('出现工具气泡', toolBubbles.length >= 2, `${toolBubbles.length} 条`);
  ok('显示「调用 xxx」', toolBubbles.some(b => /🔧|调用/.test(b.text)));
  ok('显示「xxx 完成」', toolBubbles.some(b => /✅|⚠️|完成/.test(b.text)));
  ok('气泡含工具名 predict_binding', toolBubbles.some(b => /predict_binding/.test(b.text)));
  ok('气泡含参数（alleles/peptides）', toolBubbles.some(b => /alleles|peptides/.test(b.text)));

  console.log('\n【4】回答内容含数值结论');
  ok('回答含亲和力数值', /\d+(\.\d+)?\s*nM|亲和力/.test(finalText), finalText.slice(0, 120));

  await page.screenshot({ path: path.join(SHOT_DIR, 'agent_tools_visible.png'), fullPage: false });

  console.log('\n【5】控制台');
  const real = errors.filter(e => !/favicon|net::ERR_/.test(e));
  ok('无 JS 错误', real.length === 0, real.slice(0, 2).join(' | '));

  await browser.close();
  console.log(`\n===== 合计 PASS ${pass.length} / FAIL ${fail.length} =====`);
  if (fail.length) { fail.forEach(([n, d]) => console.log(`  ✘ ${n} — ${d}`)); process.exit(1); }
})();
