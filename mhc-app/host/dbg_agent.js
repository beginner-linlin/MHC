// 226 调试：智能助手发送后发生了什么
const { chromium } = require('playwright-core');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
  page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 200)));
  page.on('console', m => console.log(`[console.${m.type()}]`, m.text().slice(0, 200)));
  page.on('response', async r => {
    if (r.url().includes('/api/agent/')) {
      console.log(`[resp] ${r.status()} ${r.url()}`);
      try {
        const b = await r.text();
        console.log('        body:', b.slice(0, 300));
      } catch {}
    }
  });

  await page.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  console.log('\n=== 切到 agent ===');
  await page.click('.nav-item[data-mode="agent"]');
  await page.waitForTimeout(800);

  const state1 = await page.evaluate(() => ({
    agentPanelHidden: document.getElementById('agentPanel')?.hidden,
    agentChatExists: !!document.getElementById('agentChat'),
    agentInputExists: !!document.getElementById('agentInput'),
    btnSendExists: !!document.getElementById('btnAgentSend'),
    btnSendDisabled: document.getElementById('btnAgentSend')?.disabled,
    chatHTML: (document.getElementById('agentChat')?.innerHTML || '').slice(0, 400),
  }));
  console.log(JSON.stringify(state1, null, 2));

  console.log('\n=== 填输入 ===');
  await page.fill('#agentInput', '用 NetMHCpan 预测 SLYNTVATL 对 HLA-A02:01 的结合');
  await page.waitForTimeout(300);
  const val = await page.inputValue('#agentInput');
  console.log('输入框值:', JSON.stringify(val));

  console.log('\n=== 点发送 ===');
  await page.click('#btnAgentSend');
  await page.waitForTimeout(2000);

  const state2 = await page.evaluate(() => ({
    chatHTML: (document.getElementById('agentChat')?.innerHTML || '').slice(0, 800),
    msgCount: document.querySelectorAll('#agentChat .msg').length,
    statusText: document.querySelector('.agent-status')?.textContent || '(none)',
  }));
  console.log(JSON.stringify(state2, null, 2));

  await page.waitForTimeout(8000);
  const state3 = await page.evaluate(() => ({
    msgCount: document.querySelectorAll('#agentChat .msg').length,
    msgs: [...document.querySelectorAll('#agentChat .msg')].map(n => ({ cls: n.className, t: n.textContent.trim().slice(0, 100) })),
  }));
  console.log('\n=== 10 秒后 ===');
  console.log(JSON.stringify(state3, null, 2));

  await page.screenshot({ path: path.join(__dirname, '..', 'run', 'shots', 'agent_dbg.png') });
  await browser.close();
})();
