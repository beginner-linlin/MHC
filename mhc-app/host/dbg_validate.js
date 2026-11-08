'use strict';
const path = require('node:path');
const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
    const browser = await chromium.launch({ executablePath: CHROME, headless: true });
    const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
    page.on('pageerror', (e) => console.log('PAGEERROR:', e.message));
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const cases = [
        ['短肽 GILG', 'GILG'],
        ['非标准 B/Z', 'GILGFVFTB\nSLYNTVATZ'],
        ['混合长度', 'SLYNTVATL\nGILGFVFTLKY'],
        ['正常', 'SLYNTVATL'],
        ['空', ''],
    ];
    for (const [name, val] of cases) {
        await page.evaluate((v) => {
            const t = document.getElementById('inputText');
            t.value = v;
            t.dispatchEvent(new Event('input', { bubbles: true }));
        }, val);
        await page.waitForTimeout(400);
        const s = await page.evaluate(() => ({
            stats: document.getElementById('inputStats').textContent,
            color: document.getElementById('inputStats').style.color,
            alertHidden: document.getElementById('alertBox').hidden,
            alertText: document.getElementById('alertBox').textContent.slice(0, 80),
        }));
        console.log(`${name.padEnd(14)} → stats="${s.stats}" color="${s.color}" alertHidden=${s.alertHidden} alert="${s.alertText}"`);
    }

    // 检查 /api/validate/input 对各种输入的真实返回
    console.log('\n=== /api/validate/input ===');
    for (const [name, val] of cases) {
        if (!val) continue;
        const r = await page.context().request.post(`${BASE}/api/validate/input`, {
            data: { input: val, input_mode: 'peptide', alleles: ['HLA-A02:01'] },
        });
        const j = await r.json().catch(() => ({}));
        console.log(`${name.padEnd(14)} status=${r.status()} warnings=${JSON.stringify(j.warnings || j.error)}`);
    }

    await browser.close();
})();
