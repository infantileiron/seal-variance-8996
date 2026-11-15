#!/usr/bin/env python3
"""汇总收包与合并方差分析 API 集成测试（需运行中的后端+数据库+Redis+worker）。

运行（仓库根目录）: API_BASE=http://127.0.0.1:18000 python3 test-artifacts/gb-3105/test_api.py
覆盖：预期范围登记、幂等收包、同号异内容/编号交叠整包拒收、缺口核查、缺包不给结论、
     合并与逐条结果一致、发起后新包不改变该次结果、并发交叠争抢、并发收包与发起分析。
"""
import math, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = os.environ.get('API_BASE', 'http://127.0.0.1:18000')
RID = f'{int(time.time()) % 1_000_000}'  # 本次运行唯一前缀，避免与既有数据冲突
FAILED = []
client = httpx.Client(base_url=BASE, timeout=30)


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')
    if not cond:
        FAILED.append((name, detail))


def req(method, path, token=None, body=None):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    r = client.request(method, path, json=body, headers=headers)
    try:
        data = r.json()
    except Exception:
        data = {}
    return r.status_code, data


def login(email):
    s, d = req('POST', '/auth/login', body={'email': email, 'password': 'Demo123!'})
    assert s == 200, f'login {email}: {s} {d}'
    return d['access_token']


def wait_done(aid, token, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s, d = req('GET', f'/assessments/{aid}', token)
        if d.get('status') in ('completed', 'failed'):
            return d
        time.sleep(0.5)
    raise TimeoutError(f'assessment {aid} 未在 {timeout}s 内结束')


def pkg_stats(values):
    n = len(values)
    m = sum(values) / n
    return n, m, math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def close(a, b, rel=1e-9):
    return math.isclose(a, b, rel_tol=rel, abs_tol=1e-12)


analyst = login('analyst@demo.local')
admin = login('admin@demo.local')
viewer = login('viewer@demo.local')
s, processes = req('GET', '/processes', analyst)
P1, P2, P3 = [p['id'] for p in processes[:3]]
print(f'== 运行前缀 {RID}，工艺 {P1}/{P2}/{P3}，目标 {BASE}')

# ---------- 1. 预期范围登记 ----------
LOT = f'T{RID}-EXP'
s, d = req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 40, 'note': ''})
check('登记预期范围 201', s == 201 and d['deduplicated'] is False, f'{s} {d}')
s, d = req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 40, 'note': ''})
check('重复登记幂等 200 不重复累计', s == 200 and d['deduplicated'] is True, f'{s} {d}')
s, d = req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 20, 'end_no': 60, 'note': ''})
check('预期范围交叠 409', s == 409, f'{s} {d}')
s, d = req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 50, 'end_no': 41, 'note': ''})
check('预期范围终点小于起点 422', s == 422, f'{s} {d}')
s, d = req('GET', f'/summary/expectations?process_id={P1}&lot={LOT}', viewer)
check('预期范围只读可查且仅 1 条', s == 200 and len(d) == 1, f'{s} {d}')

# ---------- 2. 收包：幂等、拒收、校验 ----------
LOT = f'T{RID}-PKG'
body = {'package_no': f'PK{RID}-1', 'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 10, 'n': 10, 'mean': 23.45, 'sd': 1.25, 'note': ''}
s, d = req('POST', '/summary/packages', analyst, body)
check('收包 201', s == 201 and d['deduplicated'] is False, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, body)
check('同号同内容重试 200 幂等', s == 200 and d['deduplicated'] is True, f'{s} {d}')
s, d = req('GET', f'/summary/packages?process_id={P1}&lot={LOT}', analyst)
check('重试后仍仅 1 包（不重复累计）', s == 200 and len(d) == 1, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'mean': 24.01})
check('同号异内容 409 整包拒收', s == 409 and '同号异内容' in d.get('detail', ''), f'{s} {d}')
s, d = req('GET', f'/summary/packages?process_id={P1}&lot={LOT}', analyst)
check('拒收后原包内容不变', s == 200 and len(d) == 1 and d[0]['mean'] == 23.45, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'lot': f'{LOT}-OTHER'})
check('同号跨批次异内容 409', s == 409, f'{s} {d}')
for tag, rng in [('相邻交叠', (10, 20)), ('包含交叠', (5, 15)), ('触及边界', (1, 10))]:
    s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-O{rng[0]}', 'start_no': rng[0], 'end_no': rng[1], 'n': rng[1] - rng[0] + 1})
    check(f'编号交叠（{tag}）409 整包拒收', s == 409 and '交叠' in d.get('detail', ''), f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-3', 'start_no': 11, 'end_no': 20})
check('相邻不交的包可接收 201', s == 201, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-BADN', 'start_no': 21, 'end_no': 30, 'n': 9})
check('n 不等于范围长度 422', s == 422, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-N1', 'start_no': 31, 'end_no': 31, 'n': 1})
check('n=1（无样本标准差）422', s == 422, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-SD', 'start_no': 32, 'end_no': 41, 'n': 10, 'sd': -0.5})
check('负标准差 422', s == 422, f'{s} {d}')
s, d = req('POST', '/summary/packages', analyst, {**body, 'package_no': f'PK{RID}-M0', 'start_no': 32, 'end_no': 41, 'n': 10, 'mean': 0})
check('均值超出量程 422', s == 422, f'{s} {d}')
s, d = req('POST', '/summary/packages', viewer, {**body, 'package_no': f'PK{RID}-V', 'start_no': 42, 'end_no': 51})
check('只读账号收包 403', s == 403, f'{s} {d}')

# ---------- 3. 缺口核查与合并统计量 ----------
LOT = f'T{RID}-GAP'
req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 30, 'note': ''})
v1 = [20.0 + i * 0.1 for i in range(10)]
v2 = [21.0 + i * 0.1 for i in range(20)]
n1, m1, sd1 = pkg_stats(v1)
n2, m2, sd2 = pkg_stats(v2)
req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-G1', 'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 10, 'n': n1, 'mean': m1, 'sd': sd1, 'note': ''})
s, d = req('GET', f'/summary/gaps?process_id={P1}&lot={LOT}', analyst)
check('缺口 11–30', s == 200 and d['complete'] is False and d['gaps'] == [{'start_no': 11, 'end_no': 30, 'count': 20}], f'{s} {d}')
check('缺口状态 部分缺口', d['expected'][0]['status'] == '部分缺口', f"{d['expected']}")
req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-G2', 'process_id': P1, 'lot': LOT, 'start_no': 11, 'end_no': 30, 'n': n2, 'mean': m2, 'sd': sd2, 'note': ''})
s, d = req('GET', f'/summary/gaps?process_id={P1}&lot={LOT}', analyst)
allv = v1 + v2
tn = len(allv)
tm = sum(allv) / tn
tsd = math.sqrt(sum((x - tm) ** 2 for x in allv) / (tn - 1))
check('收全后 complete=True', s == 200 and d['complete'] is True and d['gaps'] == [], f'{s} {d}')
check('合并统计量与逐条一致', d['merged']['n'] == tn and close(d['merged']['mean'], tm) and close(d['merged']['sd'], tsd), f"{d['merged']} vs {tn}/{tm}/{tsd}")

# ---------- 4. 缺包不给结论 ----------
LOT = f'T{RID}-MISS'
req('POST', '/summary/expectations', analyst, {'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 20, 'note': ''})
req('POST', '/summary/expectations', analyst, {'process_id': P2, 'lot': LOT, 'start_no': 1, 'end_no': 20, 'note': ''})
req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-M1', 'process_id': P1, 'lot': LOT, 'start_no': 1, 'end_no': 20, 'n': 20, 'mean': 23.0, 'sd': 1.1, 'note': ''})
req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-M2', 'process_id': P2, 'lot': LOT, 'start_no': 1, 'end_no': 10, 'n': 10, 'mean': 24.0, 'sd': 1.2, 'note': ''})
s, d = req('POST', '/assessments', analyst, {'title': f'缺包复核{RID}', 'lot': LOT, 'process_ids': [P1, P2], 'mode': 'summary'})
check('缺包时仍可发起（后台判定）', s == 202, f'{s} {d}')
r = wait_done(d['id'], analyst)
check('缺包不给结论', r['status'] == 'failed' and '缺包未收全' in r['error'] and '11–20' in r['error'], f"{r['status']} {r['error']}")
s, d = req('POST', '/assessments', analyst, {'title': f'汇总跨批次{RID}', 'lot': '全部', 'process_ids': [P1, P2], 'mode': 'summary'})
check('汇总模式不支持全部批次 422', s == 422, f'{s} {d}')

# ---------- 5. 合并与逐条结果一致（真实样本对照） ----------
LOT = f'T{RID}-CMP'
rng = random.Random(int(RID))
groups = {P1: [round(rng.gauss(22.5, 1.4), 3) for _ in range(24)],
          P2: [round(rng.gauss(23.2, 1.4), 3) for _ in range(24)],
          P3: [round(rng.gauss(24.1, 1.4), 3) for _ in range(24)]}
for pid, values in groups.items():
    for i, v in enumerate(values):
        s, d = req('POST', '/samples', analyst, {'code': f'S{RID}-{pid}-{i:02}', 'process_id': pid, 'lot': LOT, 'force': v, 'flagged': False, 'note': ''})
        assert s == 201, f'样本录入失败 {s} {d}'
    req('POST', '/summary/expectations', analyst, {'process_id': pid, 'lot': LOT, 'start_no': 1, 'end_no': 24, 'note': ''})
    for k in range(3):
        part = values[k * 8:(k + 1) * 8]
        n, m, sd = pkg_stats(part)
        s, d = req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-C{pid}-{k}', 'process_id': pid, 'lot': LOT, 'start_no': k * 8 + 1, 'end_no': k * 8 + 8, 'n': n, 'mean': m, 'sd': sd, 'note': ''})
        assert s == 201, f'收包失败 {s} {d}'
s, d = req('POST', '/assessments', analyst, {'title': f'逐条对照{RID}', 'lot': LOT, 'process_ids': [P1, P2, P3], 'mode': 'strip'})
strip_task = wait_done(d['id'], analyst)
s, d = req('POST', '/assessments', analyst, {'title': f'汇总对照{RID}', 'lot': LOT, 'process_ids': [P1, P2, P3], 'mode': 'summary'})
summary_task = wait_done(d['id'], analyst)
check('逐条任务完成', strip_task['status'] == 'completed', strip_task['error'])
check('汇总任务完成', summary_task['status'] == 'completed', summary_task['error'])
ra, rb = strip_task['result'], summary_task['result']
for key in ('grand_mean', 'ss_between', 'ss_within', 'ss_total', 'f', 'p', 'eta_squared'):
    check(f'合并与逐条 {key} 相符', close(ra[key], rb[key]), f"{ra[key]!r} != {rb[key]!r}")
check('合并与逐条 n 相符', ra['n'] == rb['n'] == 72, f"{ra['n']} {rb['n']}")
for ga, gb in zip(ra['groups'], rb['groups']):
    check(f"组{ga['code']} 均值/标准差相符", close(ga['mean'], gb['mean']) and close(ga['sd'], gb['sd']), f"{ga} != {gb}")
check('汇总组含包数', all(g.get('packages') == 3 for g in rb['groups']), f"{rb['groups']}")

# ---------- 6. 发起后新包不改变该次结果 ----------
s, d = req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-X1', 'process_id': P1, 'lot': LOT, 'start_no': 25, 'end_no': 40, 'n': 16, 'mean': 22.9, 'sd': 1.3, 'note': ''})
check('计划外追加包可接收', s == 201, f'{s} {d}')
s, d = req('POST', '/assessments', analyst, {'title': f'汇总对照二期{RID}', 'lot': LOT, 'process_ids': [P1, P2, P3], 'mode': 'summary'})
second = wait_done(d['id'], analyst)
s, first_again = req('GET', f"/assessments/{summary_task['id']}", analyst)
check('发起后新包不改变该次结果', first_again['result']['n'] == 72 and first_again['result']['checksum'] == rb['checksum'], f"{first_again['result']['n']}")
check('新任务纳入追加包 n=88', second['status'] == 'completed' and second['result']['n'] == 88, f"{second['status']} {second.get('error')}")

# ---------- 7. 并发交叠争抢 ----------
LOT = f'T{RID}-RACE'
def post_pkg(i, no=None, mean=23.0, start=1, end=10, lot=None):
    return req('POST', '/summary/packages', analyst, {'package_no': no or f'PK{RID}-R{i}', 'process_id': P1, 'lot': lot or LOT, 'start_no': start, 'end_no': end, 'n': end - start + 1, 'mean': mean, 'sd': 1.0, 'note': ''})
with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(post_pkg, range(8)))
codes = [r[0] for r in results]
check('并发交叠仅一个 201', codes.count(201) == 1 and codes.count(409) == 7, f'{codes}')
s, d = req('GET', f'/summary/packages?process_id={P1}&lot={LOT}', analyst)
check('并发交叠后仅 1 包落库', s == 200 and len(d) == 1, f'{s} {d}')
LOT2 = f'T{RID}-RACE2'
with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(lambda i: post_pkg(i, no=f'PK{RID}-SAME', start=1, end=10, lot=LOT2), range(8)))
codes = [r[0] for r in results]
check('并发同号同内容幂等', codes.count(201) == 1 and codes.count(200) == 7, f'{codes}')
s, d = req('GET', f'/summary/packages?process_id={P1}&lot={LOT2}', analyst)
check('并发同号同内容仅 1 包', s == 200 and len(d) == 1, f'{s} {d}')
LOT3 = f'T{RID}-RACE3'
with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(lambda i: post_pkg(i, no=f'PK{RID}-DIFF', mean=23.0 + i * 0.01, start=1, end=10, lot=LOT3), range(8)))
codes = [r[0] for r in results]
check('并发同号异内容仅一个 201 其余 409', codes.count(201) == 1 and codes.count(409) == 7, f'{codes}')
s, d = req('GET', f'/summary/packages?process_id={P1}&lot={LOT3}', analyst)
check('并发同号异内容仅 1 包落库', s == 200 and len(d) == 1, f'{s} {d}')

# ---------- 8. 并发收包与发起分析：同一已收全状态 ----------
def one_round(round_no):
    lot = f'T{RID}-CA{round_no}'
    for pid in (P1, P2):
        req('POST', '/summary/expectations', analyst, {'process_id': pid, 'lot': lot, 'start_no': 1, 'end_no': 20, 'note': ''})
    for k, (a, b) in enumerate(((1, 10), (11, 20))):
        req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-A{round_no}-{k}', 'process_id': P1, 'lot': lot, 'start_no': a, 'end_no': b, 'n': 10, 'mean': 23.0, 'sd': 1.0, 'note': ''})
    barrier = threading.Barrier(3)
    outcome = {}
    def analyze():
        barrier.wait()
        s, d = req('POST', '/assessments', analyst, {'title': f'并发分析{RID}-{round_no}', 'lot': lot, 'process_ids': [P1, P2], 'mode': 'summary'})
        outcome['task'] = (s, d)
    def receive(k, a, b):
        barrier.wait()
        time.sleep(0.02 * k)
        req('POST', '/summary/packages', analyst, {'package_no': f'PK{RID}-B{round_no}-{k}', 'process_id': P2, 'lot': lot, 'start_no': a, 'end_no': b, 'n': 10, 'mean': 24.0, 'sd': 1.1, 'note': ''})
    t = threading.Thread(target=analyze)
    t.start()
    with ThreadPoolExecutor(2) as ex:
        f1 = ex.submit(receive, 1, 1, 10)
        f2 = ex.submit(receive, 2, 11, 20)
        f1.result(); f2.result()
    t.join()
    s, d = outcome['task']
    assert s == 202, f'第{round_no}轮发起失败 {s} {d}'
    task = wait_done(d['id'], analyst)
    snap_n = sum(p['n'] for g in task['snapshot']['groups'] for p in g['packages'])
    if task['status'] == 'completed':
        ok = task['result']['n'] == snap_n == 40 and not any(g['gaps'] for g in task['snapshot']['groups'])
        return ok, f"completed n={task['result']['n']} snap_n={snap_n}"
    ok = '缺包未收全' in task['error'] and snap_n < 40
    return ok, f"failed snap_n={snap_n} err={task['error'][:40]}"
for round_no in range(5):
    ok, detail = one_round(round_no)
    check(f'并发收包与发起分析 第{round_no}轮 状态一致', ok, detail)

# ---------- 9. 逐条模式回归（保留原逐条分析） ----------
s, d = req('POST', '/assessments', analyst, {'title': f'逐条回归{RID}', 'lot': '全部', 'process_ids': [P1, P2, P3], 'mode': 'strip'})
r = wait_done(d['id'], analyst)
check('逐条模式（全部批次）回归', r['status'] == 'completed' and r['result']['n'] >= 105, f"{r['status']} {r.get('error')}")
s, d = req('POST', '/assessments', analyst, {'title': f'缺样本回归{RID}', 'lot': f'NONE-{RID}', 'process_ids': [P1, P2], 'mode': 'strip'})
r = wait_done(d['id'], analyst)
check('逐条模式样本不足记 failed', r['status'] == 'failed' and '至少需要2条' in r['error'], f"{r['status']} {r['error']}")

print()
if FAILED:
    print(f'{len(FAILED)} 项失败')
    sys.exit(1)
print('全部 API 集成测试通过')
