'use strict';
const path = require('node:path');
const { chromium } = require('playwright-core');

const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
    const browser = await chromium.launch({ executablePath: CHROME, headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    page.on('pageerror', (e) => console.log('PAGEERROR:', e.message));
    page.on('console', (m) => console.log('CONSOLE[' + m.type() + ']:', m.text().slice(0, 200)));
    page.on('requestfailed', (r) => console.log('REQFAIL:', r.url(), r.failure()?.errorText));
    page.on('response', (r) => { if (r.status() >= 400) console.log('HTTP', r.status(), r.url()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const info = await page.evaluate(() => ({
        alleleCount: window.state ? window.state.allAlleles.length : 'no window.state',
        first: window.state ? window.state.allAlleles.slice(0, 3) : [],
        hasA0201: window.state ? window.state.allAlleles.includes('HLA-A02:01') : null,
        presets: window.state ? (window.state.presets?.human?.length ?? 0) : null,
    }));
    console.log('state:', JSON.stringify(info));

    // 手动 focus + input
    await page.click('#alleleSearch');
    await page.waitForTimeout(600);
    let dd = await page.evaluate(() => {
        const d = document.getElementById('alleleDropdown');
        return { hidden: d.hidden, childCount: d.children.length, inner: d.innerText.slice(0, 200) };
    });
    console.log('focus 后 dropdown:', JSON.stringify(dd));

    await page.fill('#alleleSearch', 'A02:01');
    await page.waitForTimeout(800);
    dd = await page.evaluate(() => {
        const d = document.getElementById('alleleDropdown');
        return { hidden: d.hidden, childCount: d.children.length, inner: d.innerText.slice(0, 200), cls: [...d.children].slice(0,3).map(c=>c.className) };
    });
    console.log('输入 A02:01 后:', JSON.stringify(dd));

    await page.screenshot({ path: path.join(__dirname, '..', 'run', 'shots', 'dbg_allele.png') });
    await browser.close();
})();
