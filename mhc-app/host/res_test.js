// 资源中心浏览器端到端测试
const { chromium } = require('playwright-core');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = process.env.MHC_SHOT_DIR || 'C:\\Users\\86156\\Desktop\\大创\\软件\\整合\\mhc-workbench\\mhc-app\\run\\shots';
const fs = require('fs');
const path = require('path');

const results = [];
function ok(name, cond, extra = '') {
  results.push({ name, pass: !!cond, extra });
  console.log(`  [${cond ? 'PASS' : 'FAIL'}] ${name} ${extra}`);
}

async function shot(page, name) {
  try {
    fs.mkdirSync(SHOT, { recursive: true });
    await page.screenshot({ path: path.join(SHOT, name + '.png'), fullPage: false });
  } catch (e) { /* ignore */ }
}

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));

  try {
    // ---------- 1. 打开首页 ----------
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('.nav-item', { timeout: 15000 });
    const navCount = await page.locator('.nav-item').count();
    ok('侧栏 6 个模式', navCount === 6, `=${navCount}`);
    const hasRes = await page.locator('.nav-item[data-mode="resources"]').count();
    ok('存在「数据库与工具」入口', hasRes === 1);
    await shot(page, 'r01_home');

    // ---------- 2. 切换到资源中心 ----------
    await page.locator('.nav-item[data-mode="resources"]').click();
    await page.waitForTimeout(600);
    const resVisible = await page.locator('#resourcesPanel').isVisible();
    ok('资源面板显示', resVisible);
    const inputHidden = !(await page.locator('.panel-input').isVisible());
    ok('输入栏隐藏', inputHidden);
    const title = await page.locator('#modeTitle').textContent();
    ok('标题切换', title.includes('数据库'), `=${title}`);
    await shot(page, 'r02_resources');

    // ---------- 3. 三个子页签 ----------
    const tabs = await page.locator('.res-tabs .chip').count();
    ok('3 个子页签', tabs === 3, `=${tabs}`);
    ok('GDC 页默认显示', await page.locator('#resPaneGdc').isVisible());
    ok('IEDB 页默认隐藏', !(await page.locator('#resPaneIedb').isVisible()));

    // ---------- 4. GDC 项目下拉与驱动基因 ----------
    const projOpts = await page.locator('#gdcProject option').count();
    ok('GDC 项目下拉 8 项', projOpts === 8, `=${projOpts}`);
    const projVal = await page.locator('#gdcProject').inputValue();
    ok('默认项目 TCGA-PAAD', projVal === 'TCGA-PAAD', `=${projVal}`);
    const geneChips = await page.locator('#gdcGeneChips .chip').count();
    ok('驱动基因芯片 10 个', geneChips === 10, `=${geneChips}`);

    // ---------- 5. GDC 检索：点 KRAS 芯片 ----------
    await page.locator('#gdcGeneChips .chip', { hasText: 'KRAS' }).first().click();
    await page.waitForFunction(
      () => {
        const m = document.getElementById('gdcMeta');
        return m && !m.textContent.includes('查询中') && m.textContent.length > 0;
      },
      null,
      { timeout: 90000 },
    );
    const metaText = await page.locator('#gdcMeta').textContent();
    ok('GDC 查询返回总数', /9\s*条突变/.test(metaText), `="${metaText.slice(0, 80)}"`);
    const gdcRows = await page.locator('#gdcTbody tr').count();
    ok('GDC 结果表有行', gdcRows > 0, `=${gdcRows}`);
    const firstGene = await page.locator('#gdcTbody tr').first().locator('td').first().textContent();
    ok('首行基因=KRAS', firstGene.trim() === 'KRAS', `=${firstGene}`);
    await shot(page, 'r03_gdc');

    // ---------- 6. GDC 换基因 TP53 ----------
    await page.locator('#gdcGene').fill('TP53');
    await page.locator('#btnGdcSearch').click();
    // TP53 有 79 条突变，GDC 查询比 KRAS 慢，必须等 meta 脱离「查询中…」
    await page.waitForFunction(
      () => {
        const m = document.getElementById('gdcMeta');
        return m && !m.textContent.includes('查询中') && m.textContent.length > 0;
      },
      null,
      { timeout: 90000 },
    );
    const meta2 = await page.locator('#gdcMeta').textContent();
    ok('TP53 查询 79 条', /79\s*条突变/.test(meta2), `="${meta2.slice(0, 60)}"`);
    await shot(page, 'r04_gdc_tp53');

    // ---------- 7. IEDB 页签 ----------
    await page.locator('.res-tabs .chip[data-rtab="iedb"]').click();
    await page.waitForTimeout(400);
    ok('IEDB 页显示', await page.locator('#resPaneIedb').isVisible());
    ok('GDC 页隐藏', !(await page.locator('#resPaneGdc').isVisible()));
    const mhciMethods = await page.locator('#iedbMethod option').count();
    ok('MHC-I 方法 12 个', mhciMethods === 12, `=${mhciMethods}`);
    await shot(page, 'r05_iedb');

    // ---------- 8. IEDB 填入示例并预测 ----------
    await page.locator('#btnIedbSample').click();
    await page.waitForTimeout(300);
    const iedbStats = await page.locator('#iedbStats').textContent();
    ok('示例统计显示', /5 条肽/.test(iedbStats), `="${iedbStats}"`);
    await page.locator('#iedbAlleles').fill('HLA-A*02:01');
    await page.locator('#btnIedbRun').click();
    // IEDB 云端可能 10-60 秒
    await page.waitForFunction(
      () => {
        const m = document.getElementById('iedbMeta');
        return m && (m.textContent.includes('行结果') || m.textContent.includes('失败'));
      },
      null,
      { timeout: 120000 },
    );
    const iedbMeta = await page.locator('#iedbMeta').textContent();
    ok('IEDB 预测完成', /行结果/.test(iedbMeta), `="${iedbMeta.slice(0, 90)}"`);
    const iedbRows = await page.locator('#iedbTbody tr').count();
    ok('IEDB 结果表有行', iedbRows > 0, `=${iedbRows}`);
    await shot(page, 'r06_iedb_result');

    // ---------- 9. IEDB 切 MHC-II ----------
    await page.locator('#iedbClass').selectOption('II');
    await page.waitForTimeout(500);
    const mhciiMethods = await page.locator('#iedbMethod option').count();
    ok('MHC-II 方法 5 个', mhciiMethods === 5, `=${mhciiMethods}`);
    const lenVal = await page.locator('#iedbLength').inputValue();
    ok('MHC-II 默认肽长 15', lenVal === '15', `=${lenVal}`);

    // ---------- 10. 清单页签 ----------
    await page.locator('.res-tabs .chip[data-rtab="catalog"]').click();
    await page.waitForTimeout(400);
    ok('清单页显示', await page.locator('#resPaneCatalog').isVisible());
    const dbCards = await page.locator('#resDbGrid .res-card').count();
    ok('数据库卡片 7 个', dbCards === 7, `=${dbCards}`);
    const toolCards = await page.locator('#resToolGrid .res-card').count();
    ok('工具卡片 9 个', toolCards === 9, `=${toolCards}`);
    const badges = await page.locator('#resDbGrid .res-badge').count();
    ok('数据库卡片有状态徽标', badges === 7, `=${badges}`);
    await shot(page, 'r07_catalog');

    // ---------- 11. 卡片外链正确 ----------
    const firstLink = await page.locator('#resDbGrid .res-card a').first().getAttribute('href');
    ok('数据库卡片有外链', !!firstLink && firstLink.startsWith('http'), `=${firstLink}`);
    const firstTool = await page.locator('#resToolGrid .res-card a').first().getAttribute('href');
    ok('工具卡片有外链', !!firstTool && firstTool.startsWith('http'), `=${firstTool}`);

    // ---------- 12. 卡片上的「在此检索」按钮 ----------
    const gdcBtn = page.locator('#resDbGrid .res-card button', { hasText: '在此检索突变' }).first();
    if (await gdcBtn.count() > 0) {
      await gdcBtn.click();
      await page.waitForTimeout(500);
      ok('「在此检索突变」切回 GDC 页', await page.locator('#resPaneGdc').isVisible());
    } else {
      ok('「在此检索突变」按钮存在', false, '未找到');
    }

    // ---------- 13. 切回预测模式，功能未受影响 ----------
    await page.locator('.nav-item[data-mode="pan"]').click();
    await page.waitForTimeout(600);
    ok('切回结合预测：输入栏显示', await page.locator('.panel-input').isVisible());
    ok('切回结合预测：资源面板隐藏', !(await page.locator('#resourcesPanel').isVisible()));
    const panTitle = await page.locator('#modeTitle').textContent();
    ok('标题回到结合预测', panTitle.includes('结合'), `=${panTitle}`);

    // 快速跑一次预测确认后端未坏
    await page.locator('#btnSamplePan').click();
    await page.waitForTimeout(300);
    const beforeJob = await page.evaluate(() => window.__lastJobId || null);
    await page.locator('#btnRun').click();
    await page.waitForFunction(
      () => {
        const t = document.getElementById('rowCount');
        return t && /行/.test(t.textContent);
      },
      null,
      { timeout: 90000 },
    );
    const rowCount = await page.locator('#rowCount').textContent();
    ok('结合预测仍可运行', /行/.test(rowCount), `="${rowCount}"`);
    await shot(page, 'r08_pan_after');

    // ---------- 14. 控制台无错误 ----------
    const realErrors = consoleErrors.filter((e) => !/favicon|404/i.test(e));
    ok('控制台无错误', realErrors.length === 0, realErrors.slice(0, 2).join(' | '));

  } catch (e) {
    ok('测试异常', false, e.message);
    await shot(page, 'r99_error');
  } finally {
    const pass = results.filter((r) => r.pass).length;
    const fail = results.length - pass;
    console.log(`\n===== 合计 PASS ${pass} / FAIL ${fail} =====`);
    fs.mkdirSync(SHOT, { recursive: true });
    fs.writeFileSync(path.join(SHOT, 'resources_report.json'), JSON.stringify({ pass, fail, results }, null, 2));
    await browser.close();
  }
})();
