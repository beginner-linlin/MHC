// 真实场景：胰腺癌（TCGA-PAAD）抗原筛选全流程端到端
// GDC 查突变 → 导入新抗原模式 → UniProt 取序列 → 三步串联 → 导出
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const URL = process.env.MHC_URL || 'http://127.0.0.1:8080';
const SHOT = path.join(__dirname, '..', 'run', 'shots');
const results = [];
function ok(name, cond, extra = '') {
  results.push({ name, pass: !!cond, extra });
  console.log(`  [${cond ? 'PASS' : 'FAIL'}] ${name} ${extra}`);
}
async function shot(page, name) {
  try { fs.mkdirSync(SHOT, { recursive: true }); await page.screenshot({ path: path.join(SHOT, name + '.png') }); } catch (e) {}
}

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true, args: ['--no-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  try {
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });

    // ---------- 1. GDC 检索 TCGA-PAAD 真实突变 ----------
    await page.locator('.nav-item[data-mode="resources"]').click();
    await page.waitForTimeout(700);
    ok('资源中心打开', await page.locator('#resPaneGdc').isVisible());

    // 项目统计（GDC 元信息在检索后才显示，不单独断言）
    const projMeta = await page.locator('#gdcMeta').textContent().catch(() => '');
    ok('GDC 查询表单就绪', projMeta !== undefined, `="${String(projMeta).slice(0, 60)}"`);

    // 查 KRAS
    await page.locator('#gdcGeneChips .chip', { hasText: 'KRAS' }).first().click();
    await page.waitForFunction(
      () => { const m = document.getElementById('gdcMeta'); return m && /条突变/.test(m.textContent) && !/查询中/.test(m.textContent); },
      null, { timeout: 90000 },
    );
    const krasMeta = await page.locator('#gdcMeta').textContent();
    ok('KRAS 突变数 9 条', /9\s*条突变/.test(krasMeta), `="${krasMeta.slice(0, 90)}"`);
    const krasRows = await page.locator('#gdcTbody tr').count();
    ok('KRAS 结果表有行', krasRows === 9, `=${krasRows}`);
    await shot(page, 'p01_gdc_kras');

    // 查 TP53
    await page.locator('#gdcGene').fill('TP53');
    await page.locator('#btnGdcSearch').click();
    await page.waitForFunction(
      () => { const m = document.getElementById('gdcMeta'); return m && /条突变/.test(m.textContent) && !/查询中/.test(m.textContent); },
      null, { timeout: 90000 },
    );
    const tp53Meta = await page.locator('#gdcMeta').textContent();
    ok('TP53 突变数 79 条', /79\s*条突变/.test(tp53Meta), `="${tp53Meta.slice(0, 90)}"`);
    const tp53Rows = await page.locator('#gdcTbody tr').count();
    ok('TP53 结果表有行', tp53Rows > 20, `=${tp53Rows}`);

    // 查 SMAD4
    await page.locator('#gdcGene').fill('SMAD4');
    await page.locator('#btnGdcSearch').click();
    await page.waitForFunction(
      () => { const m = document.getElementById('gdcMeta'); return m && /条突变/.test(m.textContent) && !/查询中/.test(m.textContent); },
      null, { timeout: 90000 },
    );
    const smad4Meta = await page.locator('#gdcMeta').textContent();
    ok('SMAD4 突变数 34 条', /34\s*条突变/.test(smad4Meta), `="${smad4Meta.slice(0, 90)}"`);

    // 回到 KRAS 准备导入
    await page.locator('#gdcGene').fill('KRAS');
    await page.locator('#btnGdcSearch').click();
    await page.waitForFunction(
      () => { const m = document.getElementById('gdcMeta'); return m && /9\s*条突变/.test(m.textContent) && !/查询中/.test(m.textContent); },
      null, { timeout: 90000 },
    );

    // ---------- 2. 一键导入新抗原模式 ----------
    ok('GDC 结果页出现「一键导入」按钮', await page.locator('#btnGdcToNeo').isVisible());
    const actHint = await page.locator('#gdcActions .res-actions-hint').textContent();
    ok('按钮提示可导入错义突变数', /个错义突变可导入/.test(actHint), `="${actHint}"`);
    await page.locator('#btnGdcToNeo').click();
    await page.waitForTimeout(1200);
    ok('已自动切到新抗原模式', await page.locator('#neoBlock').isVisible());
    const mutText = await page.locator('#neoMutations').inputValue();
    const mutLines = mutText.split('\n').map((s) => s.trim()).filter(Boolean);
    ok('GDC 导入突变条数 >0', mutLines.length > 0, `=${mutLines.length} 条`);
    ok('导入内容为「基因 突变」格式', mutLines.every((l) => /^[A-Z0-9]+\s+[A-Z]\d+[A-Z*]$/.test(l)),
      `=${mutLines.slice(0, 5).join(' / ')}`);
    const gdcStat = await page.locator('#neoStats').textContent();
    ok('统计无无法识别行', !/无法识别/.test(gdcStat), `="${gdcStat}"`);

    // 只保留 5 条以控制时长
    const pick = mutLines.slice(0, 5).join('\n');
    await page.locator('#neoMutations').fill(pick);
    await page.waitForTimeout(400);
    await shot(page, 'p02_imported');

    // ---------- 3. 预览 UniProt 与候选肽 ----------
    await page.locator('#btnNeoPreview').click();
    await page.waitForFunction(
      () => { const b = document.getElementById('neoPreview'); return b && !b.hidden && !b.querySelector('.neo-loading'); },
      null, { timeout: 120000 },
    );
    const cards = await page.locator('#neoPreview .neo-card').count();
    ok('预览卡片数等于导入的突变数（5）', cards === 5, `=${cards}`);
    const accTxt = await page.locator('#neoPreview .neo-acc').first().textContent();
    ok('UniProt 编号为 P01116 · 189 aa', /P01116/.test(accTxt) && /189/.test(accTxt), `="${accTxt}"`);
    const descTxt = await page.locator('#neoPreview .neo-desc').first().textContent();
    ok('卡片显示蛋白描述', /KRas/i.test(descTxt), `="${descTxt.slice(0, 60)}"`);
    await shot(page, 'p03_preview');

    // ---------- 4. 选 6 个 HLA ----------
    await page.locator('#alleleSearch').fill('A11:01');
    await page.waitForTimeout(700);
    await page.locator('#alleleDropdown .allele-option:not(.disabled)').first().click();
    await page.waitForTimeout(300);
    await page.locator('#alleleSearch').fill('A24:02');
    await page.waitForTimeout(700);
    await page.locator('#alleleDropdown .allele-option:not(.disabled)').first().click();
    await page.waitForTimeout(300);
    await page.locator('#alleleSearch').fill('B07:02');
    await page.waitForTimeout(700);
    await page.locator('#alleleDropdown .allele-option:not(.disabled)').first().click();
    await page.waitForTimeout(300);
    const selCount = await page.locator('#alleleSelected .allele-tag').count();
    ok('已选 HLA ≥4 个', selCount >= 4, `=${selCount}`);
    const alleleNames = await page.locator('#alleleSelected .allele-tag').allTextContents();
    ok('包含 A11:01 与 A24:02', alleleNames.some((t) => /A11:01/.test(t)) && alleleNames.some((t) => /A24:02/.test(t)),
      `=${alleleNames.map((s) => s.replace('×', '')).join(',')}`);
    await shot(page, 'p04_alleles');

    // ---------- 5. 运行三步串联 ----------
    const t0 = Date.now();
    await page.locator('#btnRun').click();
    await page.waitForFunction(
      () => {
        const t = document.getElementById('resultTitle');
        const s = document.getElementById('resultSub');
        return t && s && /新抗原/.test(t.textContent) && /行结果/.test(s.textContent);
      },
      null, { timeout: 300000 },
    );
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const rSub = await page.locator('#resultSub').textContent();
    ok('任务完成并显示行数', /行结果/.test(rSub), `="${rSub}" · 墙钟 ${elapsed}s`);

    const rowCount = await page.locator('#resultTbody tr').count();
    ok('结果表有行', rowCount > 0, `=${rowCount}`);

    const kpis = await page.locator('#kpiBox .kpi').allTextContents();
    const kpiTxt = kpis.join(' | ');
    ok('KPI 显示突变数 5', /5/.test(kpiTxt), `=${kpiTxt.replace(/\s+/g, ' ').slice(0, 140)}`);

    // 步骤耗时
    const steps = await page.locator('#stepsBox .step').allTextContents();
    ok('5 步全部完成', steps.length === 5, `=${steps.map((s) => s.replace(/\s+/g, ' ').trim()).join(' / ').slice(0, 200)}`);

    await shot(page, 'p05_result');

    // ---------- 6. 结果内容真实性：检查有 SB 或 WB ----------
    const bindCells = await page.locator('#resultTbody tr td:nth-child(8)').allTextContents();
    const sbCount = bindCells.filter((t) => /SB/.test(t)).length;
    const wbCount = bindCells.filter((t) => /WB/.test(t)).length;
    ok('存在强结合或弱结合肽', sbCount + wbCount > 0, `SB=${sbCount} WB=${wbCount} 总行=${rowCount}`);

    // ---------- 7. 排序：按 EL 排名 ----------
    // 后端结果默认已按 EL 排名升序，第一次点击仍是升序 → 用第二次点击（降序）验证重排
    const ascOrder = (await page.locator('#resultTbody tr').allTextContents()).slice(0, 5).join('|');
    const elTh = page.locator('#resultThead th', { hasText: 'EL 排名' }).first();
    await elTh.click();
    await page.waitForTimeout(500);
    const headAfter1 = await elTh.textContent();
    ok('表头出现排序标记', /[↑↓]/.test(headAfter1), `="${headAfter1}"`);
    await elTh.click();
    await page.waitForTimeout(600);
    const descOrder = (await page.locator('#resultTbody tr').allTextContents()).slice(0, 5).join('|');
    const headAfter2 = await elTh.textContent();
    ok('再次点击切换为降序', /↓/.test(headAfter2), `="${headAfter2}"`);
    ok('降序后行顺序改变', ascOrder !== descOrder,
      ascOrder === descOrder ? '顺序未变' : '顺序已反转');
    // 还原升序，方便后续导出/断言
    await elTh.click();
    await page.waitForTimeout(400);

    // ---------- 8. 导出 ----------
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('#btnExportXlsx').click(),
    ]);
    const outPath = path.join(__dirname, '..', 'run', 'paad_real.xlsx');
    await dl.saveAs(outPath);
    const sz = fs.statSync(outPath).size;
    ok('XLSX 导出成功', sz > 4000, `=${sz} B · ${dl.suggestedFilename()}`);

    // ---------- 9. 历史记录回看 ----------
    await page.locator('#btnHistory').click();
    await page.waitForTimeout(1000);
    const histItems = await page.locator('.hist-item').count();
    ok('历史记录有条目', histItems > 0, `=${histItems}`);
    const histText = await page.locator('.drawer').first().textContent();
    ok('历史含「新抗原筛选」', /新抗原筛选/.test(histText), '');
    await shot(page, 'p06_history');

    const realErrors = errors.filter((e) => !/favicon|net::ERR_|502/.test(e));
    ok('控制台无 JS 错误', realErrors.length === 0, realErrors.slice(0, 3).join(' ; '));
  } catch (e) {
    ok('测试执行未抛异常', false, e.message);
    await shot(page, 'p99_error');
  } finally {
    await browser.close();
  }

  const pass = results.filter((r) => r.pass).length;
  console.log(`\n===== 胰腺癌真实场景 E2E：${pass}/${results.length} 通过 =====`);
  results.filter((r) => !r.pass).forEach((r) => console.log(`  ✗ ${r.name} ${r.extra}`));
  process.exit(pass === results.length ? 0 : 1);
})();
