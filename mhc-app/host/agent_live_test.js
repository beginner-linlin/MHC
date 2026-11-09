// agent_live_test.js — 智能助手 UI 实测：复现真实故障并抓 /api/agent/chat 响应
'use strict';
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const SHOT_DIR = path.resolve(__dirname, '..', 'run', 'shots');

(async () => {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
  const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: 'zh-CN' })).newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message.slice(0, 160)));

  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(500);

  await page.click('.nav-item[data-mode="agent"]');
  await page.waitForTimeout(800);

  // 配置状态（agentLoadCfg 写入）
  const cfgStatus = await page.locator('#agentCfgStatus').innerText().catch(() => '(无元素)');

  await page.fill('#agentInput', '你好，测试连通性');
  const sendP = page
    .waitForResponse((r) => r.url().includes('/api/agent/chat'), { timeout: 45000 })
    .catch(() => null);
  await page.click('#btnAgentSend');

  const resp = await sendP;
  let status = 'N/A', ct = 'N/A', body = 'N/A';
  if (resp) {
    status = resp.status() + ' ' + resp.statusText();
    ct = resp.headers()['content-type'] || '(none)';
    try {
      body = await Promise.race([
        resp.text(),
        new Promise((res) => setTimeout(() => res('[text() 20s 超时：流未关闭（SSE 长连接），按帧数据另查]'), 20000)),
      ]);
    } catch (e) {
      body = '(read fail: ' + e.message + ')';
    }
  } else {
    console.log('[WARN] 45s 内未捕获 /api/agent/chat 响应');
  }

  // 等页面渲染回复/错误文案
  await page.waitForTimeout(3000);
  const statusLine = await page.locator('#agentStatus').innerText().catch(() => '');
  const chatMsgs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('#agentChat .agent-msg'))
      .map((m) => '[' + m.className.replace('agent-msg', '').trim() + '] ' + m.innerText.replace(/\s+/g, ' ').slice(0, 400))
  );

  const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '').replace('T', '_');
  const shot = path.join(SHOT_DIR, 'agent_live_' + ts + '.png');
  await page.screenshot({ path: shot, fullPage: false });

  console.log('=== UI LIVE TEST ===');
  console.log('config status line :', cfgStatus);
  console.log('chat HTTP status   :', status);
  console.log('content-type       :', ct);
  console.log('response body(head):');
  console.log(String(body).slice(0, 3000));
  console.log('agentStatus        :', JSON.stringify(statusLine));
  console.log('chat messages      :');
  console.log(chatMsgs.length ? chatMsgs.join('\n') : '(空)');
  console.log('pageerror          :', errors.length ? errors.join(' | ') : '无');
  console.log('screenshot         :', shot);
  await browser.close();
})().catch((e) => { console.error('TEST FAIL:', e.message); process.exit(1); });
