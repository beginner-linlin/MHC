'use strict';
const path = require('node:path');
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = 'http://127.0.0.1:8080';
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message + ' || STACK: ' + (e.stack||'').split('\n').slice(0,3).join(' | ')));
  page.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1500);

  // 切到智能助手
  const nav = page.locator('.nav-item[data-mode="agent"]');
  console.log('agent nav count:', await nav.count());
  if (await nav.count()) {
    await nav.click();
    await page.waitForTimeout(600);
    const panelVisible = await page.locator('#agentPanel').isVisible();
    console.log('agentPanel visible:', panelVisible);
    const welcome = await page.locator('#agentWelcome').isVisible();
    console.log('welcome visible:', welcome);
    // 切到资源模式再切回，验证 agent 不残留
    await page.locator('.nav-item[data-mode="resources"]').click();
    await page.waitForTimeout(400);
    console.log('resources visible:', await page.locator('#resourcesPanel').isVisible());
    await page.locator('.nav-item[data-mode="agent"]').click();
    await page.waitForTimeout(400);
    console.log('agentPanel visible (again):', await page.locator('#agentPanel').isVisible());
    // 发送一条（无 key → 应提示配置）
    await page.fill('#agentInput', '查 EGFR 序列');
    await page.click('#btnAgentSend');
    await page.waitForTimeout(2500);
    const status = await page.locator('#agentStatus').innerText();
    const msgs = await page.locator('.agent-msg').count();
    console.log('status:', status.replace(/\s+/g,' ').slice(0,120));
    console.log('msg bubbles:', msgs);
    await page.screenshot({ path: path.join(__dirname,'..','run','shots','agent_no_key.png') });
  }
  console.log('console errors:', errs.length ? errs.slice(0,5) : 'none');
  await browser.close();
})();