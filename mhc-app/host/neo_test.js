// 新抗原一键筛选（突变 → UniProt → 三步串联）浏览器端到端测试
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots');

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
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  try {
    // ---------- 1. 打开首页，检查侧栏 ----------
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('.nav-item', { timeout: 15000 });
    const navCount = await page.locator('.nav-item').count();
    ok('侧栏 9 个模式', navCount === 9, `=${navCount}`);
    const navTexts = await page.locator('.nav-item').allTextContents();
    ok('存在「新抗原」入口', navTexts.some((t) => t.includes('新抗原')),
      `=${navTexts.map((t) => t.replace(/\s+/g, ' ').trim()).join(' | ').slice(0, 160)}`);
    await shot(page, 'n01_home');

    // ---------- 2. 切到新抗原模式 ----------
    await page.locator('.nav-item[data-mode="neoantigen"]').click();
    await page.waitForTimeout(500);
    const neoVisible = await page.locator('#neoBlock').isVisible();
    ok('突变输入块显示', neoVisible);
    const title = await page.locator('#modeTitle').textContent();
    ok('模式标题', title.includes('新抗原'), `=${title}`);
    const mainFieldHidden = !(await page.locator('.panel-input .field').first().isVisible());
    ok('普通序列输入框隐藏', mainFieldHidden);
    ok('HLA 选择框可见', await page.locator('#alleleField').isVisible());
    await shot(page, 'n02_neo_mode');

    // ---------- 3. 示例按钮 ----------
    await page.locator('#btnNeoSample').click();
    await page.waitForTimeout(300);
    const sampleVal = await page.locator('#neoMutations').inputValue();
    ok('示例填入 3 个突变', sampleVal.split('\n').filter(Boolean).length === 3,
      `="${sampleVal.replace(/\n/g, ' | ')}"`);
    const statTxt = await page.locator('#neoStats').textContent();
    ok('统计显示 3 个突变 3 个基因', /3 个突变/.test(statTxt) && /3 个基因/.test(statTxt), `="${statTxt}"`);

    // ---------- 4. 手工输入非法突变 → 统计提示 ----------
    await page.locator('#neoMutations').fill('KRAS G12D\n这不是突变\nTP53 R175H');
    await page.waitForTimeout(300);
    const statTxt2 = await page.locator('#neoStats').textContent();
    ok('非法行被计数', /1 行无法识别/.test(statTxt2), `="${statTxt2}"`);

    // ---------- 5. 非法突变点运行 → 报错提示，不发任务 ----------
    await page.locator('#btnRun').click();
    await page.waitForTimeout(700);
    const alertVisible = await page.locator('#alertBox').isVisible();
    const alertText = alertVisible ? await page.locator('#alertBox').textContent() : '';
    ok('非法突变被拦截并提示', alertVisible && /无法识别/.test(alertText), `="${alertText.slice(0, 90)}"`);
    await shot(page, 'n03_alert');

    // ---------- 6. 合法突变 + 预览 ----------
    await page.locator('#neoMutations').fill('KRAS G12D');
    await page.waitForTimeout(300);
    await page.locator('#btnNeoPreview').click();
    await page.waitForFunction(
      () => {
        const b = document.getElementById('neoPreview');
        return b && !b.hidden && !b.querySelector('.neo-loading');
      },
      null,
      { timeout: 90000 },
    );
    const cards = await page.locator('#neoPreview .neo-card').count();
    ok('预览返回蛋白卡片', cards === 1, `=${cards}`);
    const acc = await page.locator('#neoPreview .neo-acc').first().textContent();
    ok('卡片显示 UniProt 编号', /P01116/.test(acc), `="${acc}"`);
    const pepCount = await page.locator('#neoPreview .neo-pep').count();
    ok('候选肽芯片 >0', pepCount > 0, `=${pepCount}`);
    const hotCount = await page.locator('#neoPreview .neo-pep.hot').count();
    ok('标出含突变位点的肽', hotCount > 0, `=${hotCount}`);
    const mutLine = await page.locator('#neoPreview .neo-mut').first().textContent();
    ok('显示突变上下文 G→D', /G/.test(mutLine) && /D/.test(mutLine), `="${mutLine.slice(0, 60)}"`);
    await shot(page, 'n04_preview');

    // ---------- 7. 选 HLA ----------
    const presets = await page.locator('#presetRow .preset-btn').count();
    ok('有 HLA 预设按钮', presets > 0, `=${presets}`);
    let selected = await page.locator('#alleleSelected .allele-tag').count();
    ok('默认已选中至少一个 HLA', selected > 0, `=${selected}`);
    if (selected === 0 && presets > 0) {
      await page.locator('#presetRow .preset-btn').first().click();
      await page.waitForTimeout(500);
      selected = await page.locator('#alleleSelected .allele-tag').count();
    }
    // 再加一个，验证可以多选（点击未选中的预设）
    const onCount = await page.locator('#presetRow .preset-btn.on').count();
    const offBtns = page.locator('#presetRow .preset-btn:not(.on)');
    if (await offBtns.count()) {
      await offBtns.first().click();
      await page.waitForTimeout(400);
    }
    const selected2 = await page.locator('#alleleSelected .allele-tag').count();
    ok('点击可追加第二个 HLA', selected2 === selected + 1, `=${selected}→${selected2}`);
    const countTxt = await page.locator('#alleleCount').textContent();
    ok('HLA 计数与标签一致', countTxt.includes(`已选 ${selected2} 个`), `="${countTxt}"`);
    // 再点一次同一按钮应取消（toggle）
    if (await offBtns.count()) {
      await page.locator('#presetRow .preset-btn.on').last().click();
      await page.waitForTimeout(400);
      const selected3 = await page.locator('#alleleSelected .allele-tag').count();
      ok('再点一次可取消选择', selected3 === selected2 - 1, `=${selected2}→${selected3}`);
      await page.locator('#presetRow .preset-btn:not(.on)').first().click();
      await page.waitForTimeout(400);
    }
    await shot(page, 'n05_alleles');

    // ---------- 8. 运行完整任务 ----------
    await page.locator('#btnRun').click();
    await page.waitForFunction(
      () => {
        const t = document.getElementById('resultTitle');
        const s = document.getElementById('resultSub');
        return t && s && /新抗原/.test(t.textContent) && /行结果/.test(s.textContent);
      },
      null,
      { timeout: 180000 },
    );
    const rTitle = await page.locator('#resultTitle').textContent();
    ok('结果标题为「新抗原候选肽」', rTitle.includes('新抗原'), `="${rTitle}"`);
    const rSub = await page.locator('#resultSub').textContent();
    ok('结果副标题含行数与候选肽', /行结果/.test(rSub) && /候选肽/.test(rSub), `="${rSub}"`);

    const stepCount = await page.locator('#stepsBox .step').count();
    ok('步骤条显示 5 步', stepCount === 5, `=${stepCount}`);
    const stepLabels = await page.locator('#stepsBox .step strong').allTextContents();
    ok('步骤包含 UniProt / NetChop / 突变肽 / NetMHCpan / stabpan',
      stepLabels.some((s) => /UniProt/.test(s)) &&
      stepLabels.some((s) => /NetChop/.test(s)) &&
      stepLabels.some((s) => /突变肽/.test(s)) &&
      stepLabels.some((s) => /NetMHCpan/.test(s)) &&
      stepLabels.some((s) => /stabpan/.test(s)),
      `=${stepLabels.join(' | ')}`);

    const kpiLabels = await page.locator('#kpiBox .kpi-label').allTextContents();
    ok('KPI 含突变数/候选肽/结合肽', kpiLabels.some((s) => /突变/.test(s)) &&
      kpiLabels.some((s) => /候选肽/.test(s)) && kpiLabels.some((s) => /结合肽/.test(s)),
      `=${kpiLabels.join(' | ')}`);

    const rowCount = await page.locator('#resultTbody tr').count();
    ok('结果表有行', rowCount > 0, `=${rowCount}`);

    const headers = await page.locator('#resultThead th').allTextContents();
    ok('表头含基因/突变/突变肽/Δ排名',
      headers.some((s) => /基因/.test(s)) && headers.some((s) => /突变肽/.test(s)) &&
      headers.some((s) => /Δ排名/.test(s)),
      `=${headers.join(',')}`);
    await shot(page, 'n06_result');

    // ---------- 9. 表格筛选：只看 SB ----------
    await page.locator('#tableFilter').selectOption('sb').catch(() => {});
    await page.waitForTimeout(500);
    const sbRows = await page.locator('#resultTbody tr').count();
    ok('筛选 SB 后行数减少或为 0', sbRows <= rowCount, `=${sbRows}/${rowCount}`);
    await page.locator('#tableFilter').selectOption('all').catch(() => {});
    await page.waitForTimeout(300);

    // ---------- 10. 导出 ----------
    const [csvDl] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('#btnExportCsv').click(),
    ]);
    const csvName = csvDl.suggestedFilename();
    ok('CSV 导出文件名含「新抗原」', /新抗原/.test(csvName), `="${csvName}"`);
    const csvPath = path.join(SHOT, '..', 'neo_export.csv');
    await csvDl.saveAs(csvPath);
    const csvText = fs.readFileSync(csvPath, 'utf8');
    ok('CSV 含基因与肽列', /基因/.test(csvText) && /突变肽/.test(csvText),
      `第一行="${csvText.split('\r\n')[0].slice(0, 90)}"`);

    const [xlsxDl] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('#btnExportXlsx').click(),
    ]);
    const xlsxName = xlsxDl.suggestedFilename();
    ok('XLSX 导出文件名含「新抗原」', /新抗原/.test(xlsxName), `="${xlsxName}"`);
    await xlsxDl.saveAs(path.join(SHOT, '..', 'neo_export.xlsx'));
    const xsz = fs.statSync(path.join(SHOT, '..', 'neo_export.xlsx')).size;
    ok('XLSX 文件非空', xsz > 3000, `=${xsz} B`);

    // ---------- 11. 历史记录里有新抗原任务 ----------
    await page.locator('#btnHistory').click();
    await page.waitForTimeout(900);
    const drawerText = await page.locator('#historyList, .drawer-body, .drawer').first().textContent();
    ok('历史里有「新抗原筛选」', /新抗原/.test(drawerText), `="${(drawerText || '').slice(0, 100)}"`);
    await shot(page, 'n07_history');
    await page.locator('#btnCloseDrawer').click().catch(() => {});
    await page.waitForTimeout(400);

    // ---------- 12. 从 GDC 导入按钮 ----------
    await page.locator('.nav-item[data-mode="resources"]').click();
    await page.waitForTimeout(700);
    await page.locator('#gdcGeneChips .chip', { hasText: 'KRAS' }).first().click();
    await page.waitForFunction(
      () => {
        const m = document.getElementById('gdcMeta');
        return m && !m.textContent.includes('查询中') && /条突变/.test(m.textContent);
      },
      null,
      { timeout: 90000 },
    );
    await page.locator('.nav-item[data-mode="neoantigen"]').click();
    await page.waitForTimeout(500);
    await page.locator('#btnNeoFromGdc').click();
    await page.waitForTimeout(900);
    const fromGdc = await page.locator('#neoMutations').inputValue();
    ok('从 GDC 导入后突变框有内容', fromGdc.trim().length > 0,
      `="${fromGdc.replace(/\n/g, ' | ').slice(0, 100)}"`);
    ok('导入内容形如「基因 突变」', /^[A-Z0-9]+\s+[A-Z]\d+[A-Z]$/m.test(fromGdc),
      `首行="${fromGdc.split('\n')[0]}"`);
    await shot(page, 'n08_from_gdc');

    // ---------- 13. 控制台无错误 ----------
    const realErrors = errors.filter((e) => !/favicon|net::ERR_/.test(e));
    ok('控制台无 JS 错误', realErrors.length === 0, realErrors.slice(0, 3).join(' ; '));
  } catch (e) {
    ok('测试执行未抛异常', false, e.message);
    await shot(page, 'n99_error');
  } finally {
    await browser.close();
  }

  const pass = results.filter((r) => r.pass).length;
  console.log(`\n===== 新抗原模式 E2E：${pass}/${results.length} 通过 =====`);
  const failed = results.filter((r) => !r.pass);
  if (failed.length) {
    console.log('失败项：');
    failed.forEach((r) => console.log(`  - ${r.name} ${r.extra}`));
  }
  process.exit(pass === results.length ? 0 : 1);
})();
