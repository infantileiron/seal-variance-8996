#!/usr/bin/env python3
"""汇总包合并统计单元测试：合并方差分析须与原始试条逐条计算相符。

运行（仓库根目录）: PYTHONPATH=backend python3 test-artifacts/gb-3105/test_statistics.py
覆盖：随机等价性、均值接近而方差很小、大样本包、零方差守卫、缺包不给结论。
"""
import math, random, sys
from decimal import Decimal, getcontext

sys.path.insert(0, 'backend')
from src.services.statistics import anova, anova_summary, merge_stats  # noqa: E402

getcontext().prec = 50
FAILED = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')
    if not cond:
        FAILED.append((name, detail))


def close(a, b, rel=1e-9, abs_=1e-12):
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)


def pkg_stats(values):
    n = len(values)
    m = sum(values) / n
    ss = sum((v - m) ** 2 for v in values)
    return n, m, math.sqrt(ss / (n - 1))


def snapshots(groups_values, split):
    """同一批试条构造逐条快照与汇总包快照（每组按 split 分包，只保留 n/均值/样本标准差）。"""
    strip_groups, summary_groups = [], []
    for gi, values in enumerate(groups_values):
        strip_groups.append({'id': gi + 1, 'code': f'G{gi+1}', 'name': f'组{gi+1}',
                             'samples': [{'code': f'G{gi+1}-{j+1:03}', 'force': v, 'flagged': False, 'lot': 'L'} for j, v in enumerate(values)]})
        packages, start = [], 0
        bounds = [split] * (len(values) // split) + ([len(values) % split] if len(values) % split else [])
        if len(bounds) > 1 and bounds[-1] < 2:  # 末包不足2条时并入前包（每包至少2条，与收包校验一致）
            bounds[-2] += bounds[-1]
            bounds.pop()
        for pi, size in enumerate(bounds):
            part = values[start:start + size]
            n, m, sd = pkg_stats(part)
            packages.append({'id': gi * 100 + pi + 1, 'package_no': f'P{gi+1}-{pi+1}', 'start_no': start + 1,
                             'end_no': start + size, 'n': n, 'mean': m, 'sd': sd})
            start += size
        summary_groups.append({'id': gi + 1, 'code': f'G{gi+1}', 'name': f'组{gi+1}',
                               'expected': [{'start_no': 1, 'end_no': len(values)}], 'packages': packages, 'gaps': []})
    return ({'mode': 'strip', 'lot': 'L', 'groups': strip_groups},
            {'mode': 'summary', 'lot': 'L', 'groups': summary_groups})


def compare(tag, strip_snap, summary_snap, rel=1e-9):
    a, b = anova(strip_snap), anova_summary(summary_snap)
    for key in ('n', 'df_between', 'df_within'):
        check(f'{tag} {key}', a[key] == b[key], f'{a[key]} != {b[key]}')
    for key in ('grand_mean', 'ss_between', 'ss_within', 'ss_total', 'ms_between', 'ms_within', 'f', 'p', 'eta_squared'):
        check(f'{tag} {key}', close(a[key], b[key], rel), f'{a[key]!r} != {b[key]!r}')
    for ga, gb in zip(a['groups'], b['groups']):
        check(f'{tag} 组{ga["code"]} mean/sd', close(ga['mean'], gb['mean'], rel) and close(ga['sd'], gb['sd'], rel),
              f"{ga['mean']!r}/{ga['sd']!r} != {gb['mean']!r}/{gb['sd']!r}")
    return a, b


# 1) 随机等价性：2–8 组、随机分包，合并结果与逐条一致
rng = random.Random(20261115)
for trial in range(30):
    k = rng.randint(2, 8)
    groups = [[round(rng.gauss(20 + gi * 0.8, 1.5), 3) for _ in range(rng.randint(8, 60))] for gi in range(k)]
    split = rng.choice([2, 3, 5, 7])
    s_snap, m_snap = snapshots(groups, split)
    compare(f'随机#{trial}(k={k},split={split})', s_snap, m_snap)

# 2) 均值接近而方差很小：组均值仅差 1e-4 量级、组内 sd≈1e-4，不得因相消而失真
base = [23.400010, 23.400040, 23.400070]
groups = [[m + rng.gauss(0, 1e-4) for _ in range(40)] for m in base]
s_snap, m_snap = snapshots(groups, 10)
a, b = compare('均值接近方差很小', s_snap, m_snap, rel=1e-8)
check('均值接近方差很小 F 有限', math.isfinite(b['f']) and b['f'] > 0, f'f={b["f"]}')
# Decimal 高精度参照：合并 ss_within 须与高精度逐条计算一致
exact_within = Decimal(0)
for vals in groups:
    dm = sum(Decimal(repr(v)) for v in vals) / len(vals)
    exact_within += sum((Decimal(repr(v)) - dm) ** 2 for v in vals)
check('均值接近方差很小 ss_within 高精度参照', close(b['ss_within'], float(exact_within), 1e-6),
      f"{b['ss_within']!r} vs {float(exact_within)!r}")

# 3) 大样本包：每组 3 包 × 100000 条，合并 n 与统计量精确
big = [[rng.gauss(22.0 + gi, 1.2) for _ in range(300_000)] for gi in range(3)]
s_snap, m_snap = snapshots(big, 100_000)
a, b = compare('大样本包(3×100000×3)', s_snap, m_snap, rel=1e-9)
check('大样本包 总n', b['n'] == 900_000, f"n={b['n']}")

# 4) merge_stats 数值稳定
# 4a) 业务量纲（均值≈23.4、sd≈1e-4）：对照 Decimal 高精度合并，误差 <1e-9
parts = [(40, 23.400010, 1e-4), (35, 23.400040, 2e-4), (45, 23.400070, 1.5e-4)]
parts = [(n, m, (n - 1) * sd ** 2) for n, m, sd in parts]
n, mean, m2 = merge_stats(parts)
dn = sum(Decimal(p[0]) for p in parts)
dm = sum(Decimal(p[0]) * Decimal(repr(p[1])) for p in parts) / dn
dm2 = sum(Decimal(repr(p[2])) + Decimal(p[0]) * (Decimal(repr(p[1])) - dm) ** 2 for p in parts)
check('merge_stats 业务量纲 n', n == 120, f'n={n}')
check('merge_stats 业务量纲 mean', close(mean, float(dm), 1e-9), f'{mean!r} vs {float(dm)!r}')
check('merge_stats 业务量纲 m2', close(m2, float(dm2), 1e-9), f'{m2!r} vs {float(dm2)!r}')
# 4b) 大偏移小方差（均值≈1e8、sd≈1e-3，超出业务量纲的压测）：合并结果与逐条两遍法 float64 计算相符；
#     该偏移下 float64 表示误差被 n₁n₂/N 放大，两种算法同级，而朴素 E[x²]−n·mean² 公式会灾难性相消
raw_parts = [[1e8 + rng.gauss(0, 1e-3) + off for _ in range(1000)] for off in (0.001, -0.002, 0.004)]
n, mean, m2 = merge_stats([(len(v), sum(v) / len(v), sum((x - sum(v) / len(v)) ** 2 for x in v)) for v in raw_parts])
allv = [x for v in raw_parts for x in v]
sn = len(allv)
sm = sum(allv) / sn
sm2 = sum((x - sm) ** 2 for x in allv)
naive = sum(x * x for x in allv) - sn * sm * sm  # 朴素公式对照
check('merge_stats 大偏移 n', n == sn, f'{n} != {sn}')
check('merge_stats 大偏移 mean 与逐条相符', close(mean, sm, 1e-12), f'{mean!r} vs {sm!r}')
check('merge_stats 大偏移 m2 与逐条相符', close(m2, sm2, 1e-4), f'{m2!r} vs {sm2!r}')
check('Chan 合并远优于朴素公式', abs(m2 - sm2) * 100 < abs(naive - sm2), f'chan_err={abs(m2-sm2):.3e} naive_err={abs(naive-sm2):.3e}')

# 5) 组内零方差守卫：sd=0 的汇总包须明确失败
zero = [{'id': 1, 'code': 'A', 'name': 'a', 'expected': [{'start_no': 1, 'end_no': 10}],
         'packages': [{'id': 1, 'package_no': 'Z1', 'start_no': 1, 'end_no': 10, 'n': 10, 'mean': 20.0, 'sd': 0.0}], 'gaps': []},
        {'id': 2, 'code': 'B', 'name': 'b', 'expected': [{'start_no': 1, 'end_no': 10}],
         'packages': [{'id': 2, 'package_no': 'Z2', 'start_no': 1, 'end_no': 10, 'n': 10, 'mean': 21.0, 'sd': 0.0}], 'gaps': []}]
try:
    anova_summary({'mode': 'summary', 'lot': 'L', 'groups': zero})
    check('零方差守卫', False, '未抛出异常')
except ValueError as e:
    check('零方差守卫', '组内方差为零' in str(e), str(e))

# 6) 缺包不给结论：缺口或未登记预期范围时不得产出结论
gap_groups = [
    {'id': 1, 'code': 'A', 'name': 'a', 'expected': [{'start_no': 1, 'end_no': 20}],
     'packages': [{'id': 1, 'package_no': 'G1', 'start_no': 1, 'end_no': 10, 'n': 10, 'mean': 20.0, 'sd': 1.0}],
     'gaps': [{'start_no': 11, 'end_no': 20, 'count': 10}]},
    {'id': 2, 'code': 'B', 'name': 'b', 'expected': [], 'packages': [], 'gaps': []}]
try:
    anova_summary({'mode': 'summary', 'lot': 'L', 'groups': gap_groups})
    check('缺包不给结论', False, '未抛出异常')
except ValueError as e:
    check('缺包不给结论', '缺包未收全' in str(e) and 'A 缺包 11–20' in str(e) and 'B 未登记预期编号范围' in str(e), str(e))

print()
if FAILED:
    print(f'{len(FAILED)} 项失败')
    sys.exit(1)
print('全部统计单元测试通过')
