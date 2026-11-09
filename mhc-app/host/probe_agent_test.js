// 探针：智能助手「测试连接」按钮端到端验证
'use strict';
const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
    const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
    const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: 'zh-CN' })).newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message.slice(0, 100)));

    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
    // 切到智能助手
    await page.click('.nav-item[data-mode="agent"]');
    await page.waitForTimeout(500);
    // 打开设置面板
    await page.click('#btnAgentConfig');
    await page.waitForTimeout(400);
    const visible = await page.locator('#agentConfigBox').isVisible();
    // 点「测试连接」（输入框留空 → 后端用存量配置测）
    await page.click('#btnAgentTest');
    await page.waitForTimeout(6000); // 等真实上游 401 返回
    const status = await page.locator('#agentCfgStatus').innerText();
    const toasts = await page.locator('#toastStack .toast').allInnerTexts();

    console.log('设置面板可见:', visible);
    console.log('状态文本:', status);
    console.log('toast 数:', toasts.length, toasts.length ? '| 首条: ' + toasts[0].slice(0, 60) : '');
    console.log('pageerror:', errors.length ? errors.join(' | ') : '无');
    const pass = visible && status.includes('❌') && (status.includes('API Key') || status.includes('无效'));
    console.log(pass ? '[PASS] 测试连接按钮端到端可用' : '[FAIL] 按钮链路异常');
    await page.screenshot({ path: 'C:\\Users\\86156\\Desktop\\大创\\软件\\mhc-app\\run\\shots\\agent_test_btn.png', fullPage: false });
    await browser.close();
    process.exit(pass ? 0 : 1);
})().catch((e) => { console.error('PROBE FAIL:', e.message); process.exit(1); });
