#!/usr/bin/env bash
# 汇总收包与合并方差分析 · 验证入口
# 统计单元测试与前端冒烟测试本地可跑（需 python3 + backend/requirements.txt 依赖、node）。
# API 集成测试需要运行中的完整栈：docker compose up -d --build 后默认 API_BASE=http://localhost:19204
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python3}
API_BASE=${API_BASE:-http://localhost:19204}

echo '== 1/3 统计单元测试（合并与逐条相符 / 均值接近方差很小 / 大样本包 / 守卫） =='
PYTHONPATH=backend "$PY" test-artifacts/gb-3105/test_statistics.py

echo '== 2/3 前端页面冒烟测试 =='
node test-artifacts/gb-3105/test_frontend_smoke.mjs

echo '== 3/3 API 集成测试（幂等收包 / 拒收 / 缺口 / 缺包不给结论 / 快照冻结 / 并发争抢） =='
if curl -fsS --max-time 3 "$API_BASE/health" >/dev/null 2>&1; then
  API_BASE="$API_BASE" "$PY" test-artifacts/gb-3105/test_api.py
else
  echo "跳过：$API_BASE 不可达。先启动完整栈（docker compose up -d --build），或用 API_BASE 指向运行中的后端。"
fi
