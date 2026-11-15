// 前端页面渲染冒烟测试：node test-artifacts/gb-3105/test_frontend_smoke.mjs
// 用模拟数据渲染全部页面与组件，检查模板未产生 undefined/NaN/null 且包含关键标记。
import {store} from '../../frontend/src/stores/business.js';
import {processesPage} from '../../frontend/src/pages/processes.js';
import {samplesPage} from '../../frontend/src/pages/samples.js';
import {packagesPage, gapReport} from '../../frontend/src/pages/packages.js';
import {analysisPage} from '../../frontend/src/pages/analysis.js';
import {reviewsPage} from '../../frontend/src/pages/reviews.js';
import {result} from '../../frontend/src/components/common/result.js';

let failed = 0;
const check = (name, cond, detail = '') => { console.log(cond ? 'PASS' : 'FAIL', name, detail); if (!cond) failed++; };

store.user = {email: 'analyst@demo.local', role: 'analyst'};
store.processes = [
  {id: 1, code: 'HC-S1', name: '稳温基线', temperature: 160, dwell: 0.8, pressure: 0.32, note: 'n1'},
  {id: 2, code: 'HC-S2', name: '延时封合', temperature: 160, dwell: 1.2, pressure: 0.32, note: 'n2'},
];
store.samples = [{id: 1, code: 'HC-S1-001', process_id: 1, lot: 'HC-1115', force: 23.4, flagged: true, note: ''}];
store.expectations = [{id: 1, process_id: 1, lot: 'HC-1116', start_no: 1, end_no: 40, note: '', created_by: 'a@b', created_at: '2026-11-15T08:00:00+00:00'}];
store.packages = [{id: 1, package_no: 'PKG-1', process_id: 1, lot: 'HC-1116', start_no: 1, end_no: 40, n: 40, mean: 23.4, sd: 1.2, note: '', received_by: 'a@b', created_at: '2026-11-15T08:00:00+00:00'}];
const summaryResult = {mode: 'summary', n: 80, grand_mean: 23.5, ss_between: 1.2, ss_within: 90.1, ss_total: 91.3, df_between: 1, df_within: 78, ms_between: 1.2, ms_within: 1.155, f: 1.04, p: 0.31, eta_squared: 0.013, significant: false, flagged: null, checksum: 'abc', method: 'm',
  groups: [{id: 1, code: 'HC-S1', name: '稳温基线', n: 40, mean: 23.4, sd: 1.1, min: null, max: null, flagged: null, packages: 1}, {id: 2, code: 'HC-S2', name: '延时封合', n: 40, mean: 23.6, sd: 1.2, min: null, max: null, flagged: null, packages: 1}]};
const stripResult = {mode: 'strip', n: 70, grand_mean: 23.5, ss_between: 2.1, ss_within: 80.0, ss_total: 82.1, df_between: 1, df_within: 68, ms_between: 2.1, ms_within: 1.176, f: 1.79, p: 0.19, eta_squared: 0.026, significant: false, flagged: 2, checksum: 'def', method: 'm',
  groups: [{id: 1, code: 'HC-S1', name: '稳温基线', n: 35, mean: 23.4, sd: 1.1, min: 20.1, max: 25.9, flagged: 1}, {id: 2, code: 'HC-S2', name: '延时封合', n: 35, mean: 23.6, sd: 1.2, min: 20.5, max: 26.1, flagged: 1}]};
store.assessments = [
  {id: 1, title: '逐条复核', lot: 'HC-1115', status: 'completed', snapshot: {mode: 'strip', groups: stripResult.groups}, result: stripResult, error: '', recommendation: '推荐 HC-S2，需继续验证外观与封口完整性。', selected_process_id: 2, approved: false, approved_by: '', created_at: '2026-11-15T08:00:00+00:00'},
  {id: 2, title: '汇总复核', lot: 'HC-1116', status: 'completed', snapshot: {mode: 'summary', groups: summaryResult.groups}, result: summaryResult, error: '', recommendation: '', selected_process_id: null, approved: false, approved_by: '', created_at: '2026-11-15T09:00:00+00:00'},
  {id: 3, title: '缺包任务', lot: 'HC-1117', status: 'failed', snapshot: {mode: 'summary', groups: []}, result: null, error: '缺包未收全，不给结论：HC-S1 缺包 11–20', recommendation: '', selected_process_id: null, approved: false, approved_by: '', created_at: '2026-11-15T10:00:00+00:00'},
];
store.active = 2;
store.review = 1;

const pages = {processes: processesPage, samples: samplesPage, packages: packagesPage, analysis: analysisPage, reviews: reviewsPage};
for (const [name, fn] of Object.entries(pages)) {
  let html = '';
  try { html = fn(); } catch (e) { check(`页面 ${name} 渲染不抛错`, false, e.message); continue; }
  check(`页面 ${name} 渲染`, html.length > 200, '');
  check(`页面 ${name} 无 undefined/NaN/null`, !/(>|\s)(undefined|NaN|null)(<|\s)/.test(html), html.match(/.{0,40}(undefined|NaN|null).{0,40}/)?.[0] || '');
}
const pkg = packagesPage();
check('收包页含预期范围与台账', pkg.includes('预期编号范围') && pkg.includes('收包台账') && pkg.includes('PKG-1'), '');
check('收包页含核查表单', pkg.includes('id=gap-form') && pkg.includes('id=package-form') && pkg.includes('id=expectation-form'), '');
const ana = analysisPage();
check('分析页含两种模式', ana.includes('value=strip') && ana.includes('value=summary'), '');
check('分析页历史含模式标记', ana.includes('汇总包') && ana.includes('逐条'), '');
const rs = result(store.assessments[1]);
check('汇总结果含包数与缺省标记', rs.includes('1 包') && rs.includes('汇总包合并') && rs.includes('80 / —'), '');
const rt = result(store.assessments[0]);
check('逐条结果不含包数', !rt.includes('包</') && rt.includes('70 / 2'), '');
const rf = result(store.assessments[2]);
check('失败任务展示缺包原因', rf.includes('缺包未收全'), '');
const gap = gapReport({process_id: 1, process_code: 'HC-S1', lot: 'HC-1116', expected: [{id: 1, start_no: 1, end_no: 40, count: 40, received: 10, missing: [{start_no: 11, end_no: 40, count: 30}], status: '部分缺口'}], gaps: [{start_no: 11, end_no: 40, count: 30}], complete: false, outside_packages: ['PKG-X'], merged: {n: 10, mean: 23.4, sd: 1.1, packages: 1}, packages: store.packages});
check('缺口报告含缺口与计划外提示', gap.includes('11–40') && gap.includes('PKG-X') && gap.includes('部分缺口'), '');
// 只读账号
store.user = {email: 'viewer@demo.local', role: 'viewer'};
const pv = packagesPage();
check('只读账号无收包表单', !pv.includes('id=package-form') && !pv.includes('id=expectation-form'), '');
const av = analysisPage();
check('只读账号无提交表单', !av.includes('id=assessment-form'), '');

console.log();
if (failed) { console.log(`${failed} 项失败`); process.exit(1); }
console.log('全部前端冒烟测试通过');
