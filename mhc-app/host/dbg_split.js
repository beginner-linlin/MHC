// 诊断「分屏」：切到 resources / agent 模式后，打印 .layout 的网格状态与每个子元素几何
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = path.join(__dirname, '..', 'run', 'shots');

(async () => {
  fs.mkdirSync(SHOT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });

  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.nav-item');

  async function dump(mode) {
    const info = await page.evaluate((m) => {
      const layout = document.querySelector('.layout');
      const cs = getComputedStyle(layout);
      const kids = [];
      for (const el of layout.children) {
        const r = el.getBoundingClientRect();
        kids.push({
          tag: el.tagName.toLowerCase(),
          id: el.id || '',
          cls: Array.from(el.classList).join(','),
          hidden: el.hasAttribute('hidden'),
          display: getComputedStyle(el).display,
          visibility: getComputedStyle(el).visibility,
          gridCol: getComputedStyle(el).gridColumn,
          rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        });
      }
      return {
        layoutClass: layout.className,
        gridTemplateColumns: cs.gridTemplateColumns,
        kids,
      };
    }, mode);
    console.log('\n========== ' + mode + ' ==========');
    console.log('layout class: ' + info.layoutClass);
    console.log('gridTemplateColumns: ' + info.gridTemplateColumns);
    for (const k of info.kids) {
      console.log(
        `  ${k.tag}${k.id ? '#' + k.id : ''} class=[${k.cls}]` +
        ` hidden=${k.hidden} display=${k.display} gridCol=${k.gridCol}` +
        ` rect=${k.rect.x},${k.rect.y} ${k.rect.w}x${k.rect.h}`
      );
    }
    await page.screenshot({ path: path.join(SHOT, 'split_' + mode + '.png') });
  }

  await dump('pan-default');
  await page.click('.nav-item[data-mode="resources"]');
  await page.waitForTimeout(600);
  await dump('resources');
  await page.click('.nav-item[data-mode="agent"]');
  await page.waitForTimeout(600);
  await dump('agent');

  console.log('\nJS errors: ' + (errs.length ? errs.join(' | ') : 'none'));
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(2); });
