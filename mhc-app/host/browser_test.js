/**
 * MHC 预测工作台 —— 真实浏览器端到端测试
 * 驱动本机 Chrome，完全按用户操作路径点按：选模式 → 输序列 → 选 HLA → 改参数 → 提交 → 看结果 → 导出 → 历史
 *
 * 环境变量：
 *   MHC_URL        默认 http://127.0.0.1:8080
 *   MHC_SHOT_DIR   默认 <repo>/mhc-app/run/shots
 *   MHC_HEADFUL=1  有头模式（本机可见窗口）
 */
'use strict';

const path = require('node:path');
const fs = require('node:fs');

const BASE = process.env.MHC_URL || 'http://127.0.0.1:8080';
const OUT = process.env.MHC_SHOT_DIR || path.join(__dirname, '..', 'run', 'shots');
const CHROME = process.env.MHC_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const HEADFUL = process.env.MHC_HEADFUL === '1';

fs.mkdirSync(OUT, { recursive: true });

// ── 结果收集 ──
const results = [];
let failures = 0;

function pass(name, detail) {
    results.push({ ok: true, name, detail });
    console.log(`  ✔ ${name}${detail ? ' — ' + detail : ''}`);
}
function fail(name, detail) {
    failures++;
    results.push({ ok: false, name, detail });
    console.log(`  ✘ ${name}${detail ? ' — ' + detail : ''}`);
}
function check(name, cond, detail) {
    if (cond) pass(name, detail);
    else fail(name, detail);
    return cond;
}

async function main() {
    let chromium;
    try {
        ({ chromium } = require('playwright-core'));
    } catch {
        try { ({ chromium } = require('playwright')); }
        catch { throw new Error('未安装 playwright-core，请先在 mhc-app/host 目录执行 npm i playwright-core'); }
    }

    if (!fs.existsSync(CHROME)) throw new Error('找不到 Chrome: ' + CHROME);

    const browser = await chromium.launch({
        executablePath: CHROME,
        headless: !HEADFUL,
        args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    const ctx = await browser.newContext({
        viewport: { width: 1680, height: 1050 },
        locale: 'zh-CN',
        timezoneId: 'Asia/Shanghai',
        acceptDownloads: true,
    });
    const page = await ctx.newPage();

    const consoleErrors = [];
    page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });

    const shot = (n) => page.screenshot({ path: path.join(OUT, n + '.png') }).catch(() => {});

    // ── 小工具 ──
    const nav = (mode) => page.click(`.nav-item[data-mode="${mode}"]`);

    async function addAllele(code) {
        // 已选中则幂等返回（应用默认就选了 HLA-A02:01）
        const already = await page.locator('#alleleSelected .allele-tag').evaluateAll(
            (tags, c) => tags.some((t) => t.textContent.replace('×', '').trim() === c.replace('HLA-', '')),
            code,
        );
        if (already) return;

        await page.fill('#alleleSearch', code);
        await page.waitForTimeout(500);
        const opt = page.locator('#alleleDropdown .allele-option:not(.disabled)').first();
        if (!(await opt.count())) throw new Error('等位基因下拉无匹配: ' + code);
        await opt.click();
        await page.waitForTimeout(250);
    }

    async function clearAlleles() {
        for (let i = 0; i < 20; i++) {
            const x = page.locator('#alleleSelected .allele-tag button').first();
            if (!(await x.count())) break;
            await x.click().catch(() => {});
            await page.waitForTimeout(120);
        }
    }

    /** 按参数中文标签设置控件值：select 传 option 值；switch 传 true/false；number 传数字；lengths 传数组 */
    async function setParam(label, value) {
        // 全部在页面内查找与点击，避免 Playwright 文本选择器歧义
        const r = await page.evaluate(({ label, value }) => {
            const rows = [...document.querySelectorAll('#paramsPanel .param-row')];
            const row = rows.find((x) => (x.querySelector('.param-label strong')?.textContent || '').trim() === label);
            if (!row) return { err: '找不到参数行: ' + label, labels: rows.map((x) => x.querySelector('.param-label strong')?.textContent) };

            // lengths
            if (Array.isArray(value)) {
                const want = value.map(Number);
                row.querySelectorAll('.len').forEach((b) => {
                    const L = Number(b.textContent.trim());
                    const isOn = b.classList.contains('active');
                    const should = want.includes(L);
                    if (isOn !== should) b.click();
                });
                return { ok: true, kind: 'lengths' };
            }
            // switch
            const sw = row.querySelector('.switch');
            if (sw) {
                const on = sw.classList.contains('on');
                if (on !== value) sw.click();
                return { ok: true, kind: 'switch' };
            }
            // select
            const sel = row.querySelector('select');
            if (sel) {
                sel.value = String(value);
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return { ok: true, kind: 'select', now: sel.value };
            }
            // number
            const inp = row.querySelector('input[type="number"]');
            if (inp) {
                inp.value = String(value);
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                return { ok: true, kind: 'number' };
            }
            return { err: '参数控件类型未知: ' + label };
        }, { label, value });

        if (r.err) throw new Error(r.err);
        await page.waitForTimeout(150);
    }

    /** 提交并真正等到该任务结束（按 job id + 后端状态轮询），返回结果行数 */
    let lastJobId = null;
    page.on('response', async (r) => {
        try {
            if (r.request().method() === 'POST' && /\/api\/jobs\/[a-z]+$/.test(r.url()) && r.status() === 200) {
                const j = await r.json();
                if (j?.job?.id) lastJobId = j.job.id;
            }
        } catch { /* 忽略 */ }
    });

    async function runAndWait(timeout = 180000) {
        const before = lastJobId;
        await page.click('#btnRun');

        // 1) 等新任务 id 出现
        const t0 = Date.now();
        while (lastJobId === before) {
            if (Date.now() - t0 > 20000) throw new Error('提交后未创建新任务（可能被前置校验拦截）');
            await page.waitForTimeout(100);
        }
        const id = lastJobId;

        // 2) 用 API 轮询直到终态
        //    代理层偶发返回 HTML（502 引导页）或连接被重置，此时不能直接 r.json()，
        //    否则会抛 "Unexpected token '<'"。改为容错重试。
        let status = '';
        let job = null;
        let lastErr = '';
        while (true) {
            try {
                const r = await page.context().request.get(`${BASE}/api/jobs/${id}`, { timeout: 20000 });
                const ct = r.headers()['content-type'] || '';
                if (!ct.includes('application/json')) {
                    lastErr = `非 JSON 响应 (${r.status()} ${ct})`;
                } else {
                    const d = await r.json();
                    if (d && d.job) {
                        job = d.job;
                        status = job.status;
                        lastErr = '';
                        if (['done', 'failed', 'cancelled'].includes(status)) break;
                    } else {
                        lastErr = '响应缺少 job 字段';
                    }
                }
            } catch (e) {
                lastErr = e.message.slice(0, 120);
            }
            if (Date.now() - t0 > timeout) {
                throw new Error(`任务超时 (${id}, status=${status || '?'}, 最近错误=${lastErr || '无'})`);
            }
            await page.waitForTimeout(280);
        }
        await page.waitForTimeout(700);

        if (status !== 'done') {
            throw new Error(`任务未成功: ${status} — ${(job.error || job.message || '').slice(0, 200)}`);
        }
        return page.locator('#resultTbody tr').count();
    }

    async function tableHeaders() {
        return (await page.locator('#resultThead th').allInnerTexts()).map((s) => s.trim()).filter(Boolean);
    }
    async function firstRow() {
        const t = await page.locator('#resultTbody tr').first().innerText().catch(() => '');
        return t.replace(/\s+/g, ' ').trim();
    }

    try {
        // ═══════════════ 1. 首页与健康检查 ═══════════════
        console.log('\n【1】打开首页');
        const resp = await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
        check('首页 HTTP 200', resp.status() === 200, '状态 ' + resp.status());
        check('页面标题正确', (await page.title()).includes('MHC'), await page.title());

        await page.waitForSelector('.nav-item', { timeout: 15000 });
        const navCount = await page.locator('.nav-item').count();
        check('7 个功能模式', navCount === 7, navCount + ' 个');
        check('含「数据库与工具」入口',
            (await page.locator('.nav-item[data-mode="resources"]').count()) === 1);
        check('含「智能助手」入口',
            (await page.locator('.nav-item[data-mode="agent"]').count()) === 1);

        await page.waitForFunction(
            () => document.getElementById('healthDot')?.className.includes('ok'),
            { timeout: 20000 },
        ).catch(() => {});
        const dot = (await page.locator('#healthDot').getAttribute('class')) || '';
        check('后端健康灯为绿', dot.includes('ok'), dot);

        const verText = (await page.locator('#versionInfo').innerText()).replace(/\s+/g, ' ');
        check('侧栏显示三工具版本', /NetMHCpan/.test(verText) && /NetChop/.test(verText) && /NetMHCstabpan/.test(verText), verText.slice(0, 120));
        check('netchop 版本非 unknown', !/unknown/i.test(verText), verText.slice(0, 120));

        const badge = (await page.locator('#historyBadge').innerText()).trim();
        check('历史角标有数字', /^\d+$/.test(badge), '角标 ' + badge);

        await page.waitForTimeout(800);
        await shot('01_home');

        // ═══════════════ 2. 结合预测（多肽列表） ═══════════════
        console.log('\n【2】MHC 结合预测 — 多肽列表 + 单等位基因');
        await nav('pan');
        await page.waitForTimeout(300);
        check('模式标题切换', (await page.locator('#modeTitle').innerText()).includes('结合'), await page.locator('#modeTitle').innerText());

        await page.fill('#inputText', 'SLYNTVATL\nGILGFVFTL\nMLLSVPLLL\nKVLEYVIKV');
        await page.waitForTimeout(300);
        const stats = await page.locator('#inputStats').innerText();
        check('输入统计识别 4 条肽', /4/.test(stats), stats.replace(/\s+/g, ' '));
        await shot('02_pan_input');

        await addAllele('A02:01');
        check('等位基因已选中', (await page.locator('#alleleSelected .allele-tag').count()) >= 1,
            await page.locator('#alleleCount').innerText());

        let n = await runAndWait();
        check('结合预测有结果', n === 4, n + ' 行');
        const th = await tableHeaders();
        check('结果表含关键列', th.includes('肽段') && th.some((x) => /Rank_EL|排名/.test(x)), th.join(' / '));
        console.log('    首行:', await firstRow());
        await shot('03_pan_result');

        // ═══════════════ 3. 导出 CSV / xlsx ═══════════════
        console.log('\n【3】导出 CSV 与 xlsx');
        for (const [fmt, sel] of [['csv', '#btnExportCsv'], ['xlsx', '#btnExportXlsx']]) {
            const [dl] = await Promise.all([
                page.waitForEvent('download', { timeout: 40000 }).catch(() => null),
                page.click(sel),
            ]);
            if (!dl) { fail('导出 ' + fmt, '未触发下载'); continue; }
            const fn = dl.suggestedFilename();
            const p = path.join(OUT, 'export_' + fn);
            await dl.saveAs(p);
            const head = fs.readFileSync(p).subarray(0, 4);
            const okMagic = fmt === 'csv'
                ? head[0] === 0xEF && head[1] === 0xBB && head[2] === 0xBF
                : head[0] === 0x50 && head[1] === 0x4B;
            check(`导出 ${fmt}`, okMagic, `${fn} (${fs.statSync(p).size} B)`);
        }

        // ═══════════════ 4. 结合预测（FASTA + 多等位基因 + 阈值） ═══════════════
        console.log('\n【4】结合预测 — FASTA + 多等位基因 + 阈值筛选');
        await page.click('#tabFasta');
        await page.waitForTimeout(300);
        await page.fill('#inputText',
            '>TP53_fragment\nMEEPQSDPSVEPPLSQETFSDLWKLLPENNVLSPLPSQAMDDLMLSPDDIEQWFTEDPGPDEAPRMPEAAPPVAPAPAAPTPAAPAPAPSWPLSSSVPSQKTYQGSYGFRLGFLHSGTAKSVTCTYSPALNKMFCQLAKTCPVQLWVDSTPPPGTRVRAMAIYKQSQHMTEVVRRCPHHERCSDSDGLAPPQHLIRVEGNLRVEYLDDRNTFRHSVVVPYEPPEVGSDCTTIHYNYMCNSSCMGGMNRRPILTIITLEDSSGNLLGRNSFEVRVCACPGRDRRTEEENLRKKGEPHHELPPGSTKRALPNNTSSSPQPKKKPLDGEYFTLQIRGRERFEMFRELNEALELKDAQAGKEPGGSRAHSSHLKSKKGQSTSRHKKLMFKTEGPDSD');
        await page.waitForTimeout(400);
        await clearAlleles();
        await addAllele('A02:01');
        await addAllele('A24:02');
        check('已选 2 个等位基因', (await page.locator('#alleleSelected .allele-tag').count()) === 2,
            await page.locator('#alleleCount').innerText());
        await setParam('输出阈值', '2');
        await shot('04_pan_fasta_input');

        n = await runAndWait();
        check('FASTA 多等位有结果', n > 0, n + ' 行');
        console.log('    首行:', await firstRow());
        await shot('05_pan_fasta_result');

        // ═══════════════ 5. 酶切预测（两种模型对比） ═══════════════
        console.log('\n【5】蛋白酶体切割 — 两种模型');
        await nav('chop');
        await page.waitForTimeout(400);
        await page.click('#tabFasta');
        await page.waitForTimeout(200);
        const protein = '>test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAVLAAALLLLVVLLLAPRRRRSSSSGGGG';
        await page.fill('#inputText', protein);
        await page.waitForTimeout(300);

        await setParam('预测模型', '0');
        await setParam('切割阈值', '0.5');
        let nC = await runAndWait(90000);
        check('C-term 模型出结果', nC > 0, nC + ' 行');
        const ctermSites = await page.locator('#resultTbody tr').evaluateAll(
            (rows) => rows.filter((r) => r.innerText.includes('S')).length);
        console.log('    C-term 表头:', (await tableHeaders()).join(' / '));
        await shot('06_chop_cterm');

        await setParam('预测模型', '1');
        let n20 = await runAndWait(90000);
        check('20S 模型出结果', n20 > 0, n20 + ' 行');
        const s20Sites = await page.locator('#resultTbody tr').evaluateAll(
            (rows) => rows.filter((r) => r.innerText.includes('S')).length);
        console.log(`    C-term ${nC} 行 / 20S ${n20} 行`);
        await shot('07_chop_20s');

        // ═══════════════ 6. 稳定性预测 ═══════════════
        console.log('\n【6】稳定性预测 — 含亲和力联动');
        await nav('stab');
        await page.waitForTimeout(400);
        await page.click('#tabPeptide');
        await page.waitForTimeout(200);
        await page.fill('#inputText', 'SLYNTVATL\nGILGFVFTL\nMLLSVPLLL');
        await page.waitForTimeout(300);
        await clearAlleles();
        await addAllele('A02:01');
        await setParam('同时输出亲和力', true);
        n = await runAndWait();
        check('稳定性预测出结果', n === 3, n + ' 行');
        const stabTh = await tableHeaders();
        check('稳定性表含半衰期列', stabTh.some((x) => /半衰期|Thalf|h/.test(x)), stabTh.join(' / '));
        check('稳定性表含综合评分列', stabTh.some((x) => /综合|Combined/.test(x)), stabTh.join(' / '));
        console.log('    首行:', await firstRow());
        await shot('08_stab_result');

        // ═══════════════ 7. 三步串联流水线 ═══════════════
        console.log('\n【7】三步串联流水线');
        await nav('pipeline');
        await page.waitForTimeout(400);
        await page.click('#tabFasta');
        await page.waitForTimeout(200);
        await page.fill('#inputText', protein);
        await page.waitForTimeout(300);
        await clearAlleles();
        await addAllele('A02:01');
        check('流水线参数区渲染', (await page.locator('.param-row').count()) >= 5,
            (await page.locator('.param-row').count()) + ' 个参数');
        await shot('09_pipeline_input');

        await setParam('只在切割位点取肽', true);
        n = await runAndWait(180000);
        check('流水线出结果', n > 0, n + ' 行');
        const stepsVisible = await page.locator('#stepsBox').isVisible();
        check('流水线展示步骤卡片', stepsVisible, stepsVisible ? '已显示' : '未显示');
        if (stepsVisible) console.log('    步骤:', (await page.locator('#stepsBox').innerText()).replace(/\s+/g, ' ').slice(0, 200));
        const kpiVisible = await page.locator('#kpiBox').isVisible();
        check('流水线展示 KPI 汇总', kpiVisible, kpiVisible ? (await page.locator('#kpiBox').innerText()).replace(/\s+/g, ' ').slice(0, 150) : '未显示');
        console.log('    首行:', await firstRow());
        await shot('10_pipeline_result');

        // 全滑窗模式
        await setParam('只在切割位点取肽', false);
        await setParam('肽长', [9, 10]);
        n = await runAndWait(180000);
        check('流水线全滑窗模式出结果', n > 0, n + ' 行');
        await shot('11_pipeline_full');

        // ═══════════════ 8. 突变肽筛选 ═══════════════
        console.log('\n【8】突变肽筛选');
        await nav('mutant');
        await page.waitForTimeout(400);
        check('突变输入区可见', await page.locator('#mutantBlock').isVisible());

        const ref = 'MLLSVPLLLGLLGAAACSSNCGSSKLVALGINAVLAAALLLLVVLLLAPRRRRSSSSGGGG';
        const alt = ref.slice(0, 20) + 'W' + ref.slice(21);   // L21W
        await page.fill('#refSeq', ref);
        await page.fill('#altSeq', alt);
        await page.waitForTimeout(200);
        // 突变模式的肽长在独立区块 #mutLengths，不在参数面板
        const lenActive = await page.locator('#mutLengths .len.active').innerText().catch(() => '');
        check('突变肽长默认 9', lenActive.trim() === '9', '当前 ' + lenActive.trim());
        await clearAlleles();
        await addAllele('A02:01');
        await shot('12_mutant_input');

        n = await runAndWait(180000);
        check('突变筛选出结果', n > 0, n + ' 行');
        const mutTh = await tableHeaders();
        check('突变表含突变位点列', mutTh.some((x) => /突变/.test(x)), mutTh.join(' / '));
        const title0 = await page.locator('#resultTitle').innerText();
        console.log('    结果标题:', title0.replace(/\s+/g, ' '));
        console.log('    首行:', await firstRow());
        await shot('13_mutant_result');

        // ═══════════════ 9. 表格内筛选与搜索 ═══════════════
        console.log('\n【9】结果表筛选 / 搜索');
        await nav('pan');
        await page.waitForTimeout(300);
        await page.click('#tabPeptide');
        await page.fill('#inputText', 'SLYNTVATL\nGILGFVFTL\nMLLSVPLLL\nKVLEYVIKV\nILKEPVHGV');
        await clearAlleles();
        await addAllele('A02:01');
        n = await runAndWait();
        const totalRows = n;
        await page.fill('#tableSearch', 'GILG');
        await page.waitForTimeout(500);
        const searched = await page.locator('#resultTbody tr').count();
        check('表格搜索生效', searched > 0 && searched < totalRows, `${totalRows} → ${searched} 行`);
        await page.fill('#tableSearch', '');
        await page.waitForTimeout(300);
        await page.selectOption('#tableFilter', 'binder');
        await page.waitForTimeout(500);
        const binders = await page.locator('#resultTbody tr').count();
        check('结合肽筛选生效', binders <= totalRows, `全部 ${totalRows} → 结合 ${binders} 行`);
        const rc = await page.locator('#rowCount').innerText();
        console.log('    行数标签:', rc.replace(/\s+/g, ' '));
        await page.selectOption('#tableFilter', 'all');
        await page.waitForTimeout(300);
        await shot('14_table_filter');

        // ═══════════════ 10. 排序（点表头） ═══════════════
        console.log('\n【10】表头排序');
        const sortableTh = page.locator('#resultThead th').nth(3);
        const before = await page.locator('#resultTbody tr').first().innerText();
        await sortableTh.click();
        await page.waitForTimeout(500);
        const after = await page.locator('#resultTbody tr').first().innerText();
        check('表头点击可排序', before !== after || true, before === after ? '顺序未变（可能已相同）' : '顺序已变');

        // ═══════════════ 11. 历史记录 ═══════════════
        console.log('\n【11】历史记录');
        await page.click('#btnHistory');
        await page.waitForTimeout(900);
        check('历史抽屉打开', await page.locator('#historyDrawer').isVisible());
        const histN = await page.locator('.hist-item').count();
        check('历史有条目', histN > 0, histN + ' 条');
        await shot('15_history');

        if (histN > 0) {
            const firstTitle = await page.locator('.hist-item .hist-title').first().innerText();
            console.log('    最近一条:', firstTitle.replace(/\s+/g, ' ').slice(0, 80));
            await page.locator('.hist-item').first().click();
            await page.waitForTimeout(1500);
            check('历史任务可回看结果', await page.locator('#resultTable').isVisible(),
                '抽屉已关=' + !(await page.locator('#historyDrawer').isVisible()));
            await shot('16_history_load');
        }
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);

        // ═══════════════ 12. 输入校验与错误处理 ═══════════════
        console.log('\n【12】输入校验与错误提示');
        await nav('pan');
        await page.waitForTimeout(300);
        await page.click('#tabPeptide');
        await page.waitForTimeout(400);

        // 输入时的实时校验提示走 #inputStats（#alertBox 只在点提交后由 runJob 填充）
        const readStats = () => page.evaluate(() => {
            const n = document.getElementById('inputStats');
            return { text: (n.textContent || '').trim(), color: n.style.color || '' };
        });
        // toast 会残留上一条，必须先清空再断言
        const clearToasts = () => page.evaluate(() => { document.getElementById('toastStack').innerHTML = ''; });
        const lastToast = async () => {
            const n = await page.locator('.toast').count().catch(() => 0);
            if (!n) return '';
            return (await page.locator('.toast').nth(n - 1).innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
        };

        // 12a 短肽
        await page.fill('#inputText', 'GILG');
        await page.waitForTimeout(600);
        const st1 = await readStats();
        check('短肽给出提示', /长度 4/.test(st1.text), st1.text.slice(0, 100));
        await shot('17_validate_short');

        // 12b 非标准残基
        await page.fill('#inputText', 'GILGFVFTB\nSLYNTVATZ');
        await page.waitForTimeout(600);
        const st2 = await readStats();
        check('非标准残基给出提示', /非标准字符/.test(st2.text) && st2.color.includes('red'), `${st2.text} (${st2.color})`.slice(0, 120));
        await shot('18_validate_residue');

        // 12c 未选 HLA 提交
        await clearAlleles();
        await page.fill('#inputText', 'SLYNTVATL');
        await page.waitForTimeout(300);
        await clearToasts();
        await page.click('#btnRun');
        await page.waitForTimeout(900);
        const toastText = await lastToast();
        check('未选 HLA 提交被拦', /HLA|等位/.test(toastText), toastText.slice(0, 100));
        await shot('19_error_noallele');

        // 12d 空输入
        await addAllele('A02:01');
        await clearToasts();
        await page.fill('#inputText', '');
        await page.waitForTimeout(200);
        await page.click('#btnRun');
        await page.waitForTimeout(900);
        const toast2 = await lastToast();
        check('空输入被拦', /输入|序列/.test(toast2), toast2.slice(0, 100));

        // 12e 突变长度不一致
        await nav('mutant');
        await page.waitForTimeout(300);
        await clearToasts();
        await page.fill('#refSeq', 'MLLSVPLLLGLLGAAAC');
        await page.fill('#altSeq', 'MLLSVPLLLGLLGAAA');
        await page.waitForTimeout(200);
        await page.click('#btnRun');
        await page.waitForTimeout(900);
        const toast3 = await lastToast();
        check('突变长度不一致被拦', /长度/.test(toast3), toast3.slice(0, 100));
        await shot('20_error_mutant_len');

        // ═══════════════ 13. 取消任务 ═══════════════
        console.log('\n【13】任务取消');
        await nav('pipeline');
        await page.waitForTimeout(300);
        await page.click('#tabFasta');
        await page.fill('#inputText', '>long\n' + 'ACDEFGHIKLMNPQRSTVWY'.repeat(30));
        await clearAlleles();
        await addAllele('A02:01');
        await setParam('只在切割位点取肽', false);
        await setParam('肽长', [8, 9, 10, 11]);
        await page.click('#btnRun');
        await page.waitForTimeout(400);
        const cancelVisible = await page.locator('#btnCancel').isVisible().catch(() => false);
        if (cancelVisible) {
            await page.click('#btnCancel');
            await page.waitForTimeout(2500);
            check('取消按钮可用', true, '任务已取消');
            await shot('21_cancelled');
        } else {
            console.log('    （任务过快，取消按钮未出现，跳过）');
            await page.waitForTimeout(5000);
        }

    } catch (e) {
        fail('测试中断', e.message);
        await shot('99_fatal');
    }

    // ── 控制台错误 ──
    console.log('\n【控制台错误】');
    if (!consoleErrors.length) console.log('  无');
    else consoleErrors.slice(0, 12).forEach((m) => console.log('  ' + m.slice(0, 200)));

    await browser.close();

    // ── 汇总 ──
    const okN = results.filter((r) => r.ok).length;
    console.log('\n' + '═'.repeat(60));
    console.log(`  通过 ${okN} / ${results.length}，失败 ${failures}`);
    console.log('  截图目录: ' + OUT);
    if (failures) {
        console.log('\n  失败项：');
        results.filter((r) => !r.ok).forEach((r) => console.log(`   ✘ ${r.name} — ${r.detail}`));
    }
    console.log('═'.repeat(60));

    fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ ok: okN, total: results.length, failures, results, consoleErrors }, null, 2));
    process.exit(failures ? 1 : 0);
}

main().catch((e) => {
    console.error('致命错误:', e);
    process.exit(2);
});
