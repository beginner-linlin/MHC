'use strict';
const path = require('node:path');
const { chromium } = require('playwright-core');
const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
    const browser = await chromium.launch({ executablePath: CHROME, headless: true });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    for (const mode of ['pan', 'chop', 'stab', 'pipeline', 'mutant']) {
        await page.click(`.nav-item[data-mode="${mode}"]`);
        await page.waitForTimeout(500);
        const dump = await page.evaluate(() => {
            const box = document.getElementById('paramsPanel');
            return {
                rowCount: box.querySelectorAll('.param-row').length,
                rows: [...box.querySelectorAll('.param-row')].map((r) => ({
                    labelHTML: r.querySelector('.param-label')?.innerHTML || '',
                    strongText: r.querySelector('.param-label strong')?.textContent,
                    ctl: r.querySelector('.param-control')?.firstElementChild?.tagName,
                    ctlClass: r.querySelector('.param-control')?.firstElementChild?.className,
                    options: [...(r.querySelectorAll('option') || [])].map((o) => `${o.value}=${o.textContent}`),
                })),
            };
        });
        console.log(`\n[${mode}] ${dump.rowCount} 行`);
        dump.rows.forEach((r, i) => console.log(`  ${i}: strong="${r.strongText}" ctl=${r.ctl}.${r.ctlClass} opts=${JSON.stringify(r.options)}`));
    }

    // 也检查 FASTA 输入切换是否真的换了 placeholder / 内容
    console.log('\n--- 输入区状态 ---');
    for (const t of ['tabPeptide', 'tabFasta']) {
        await page.click('#' + t);
        await page.waitForTimeout(400);
        const s = await page.evaluate(() => ({
            value: document.getElementById('inputText').value.slice(0, 40),
            placeholder: document.getElementById('inputText').placeholder.slice(0, 40),
            stats: document.getElementById('inputStats').textContent,
        }));
        console.log(`  ${t}: value="${s.value}" ph="${s.placeholder}" stats="${s.stats}"`);
    }

    await page.screenshot({ path: path.join(__dirname, '..', 'run', 'shots', 'dbg_params.png') });
    await browser.close();
})();
