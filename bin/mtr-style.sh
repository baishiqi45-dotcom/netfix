#!/usr/bin/env bash
# mtr-style.sh — 多次 ping + traceroute + 丢包/抖动统计（不依赖 mtr）
# 对应 final.md §5.1 ping/traceroute/mtr
# 用法：bash bin/mtr-style.sh [目标] [轮数]  默认 example.com 3
#       bash bin/mtr-style.sh example.com deep   # 加跑多轮叠加分析

set -uo pipefail

TARGET="${1:-example.com}"
ROUNDS="${2:-3}"
DEEP=""
[[ "${3:-}" == "deep" || "$ROUNDS" == "deep" ]] && DEEP=1

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

hr "[1/3] 解析目标"
IP=$(dig +short +time=3 +tries=1 "$TARGET" 2>/dev/null | head -1)
if [[ -z "$IP" ]]; then
  err "解析 $TARGET 失败 — 跳到 bin/dns-check.sh"
  exit 1
fi
echo "目标: $TARGET → $IP"

hr "[2/3] 多次 ping 统计（$ROUNDS 轮，每轮 10 包）"
PING_ALL=$(ping -c $((ROUNDS * 10)) -W 2 "$TARGET" 2>&1)
echo "$PING_ALL" | tail -3
LOSS=$(echo "$PING_ALL" | awk '/packet loss/{print $7}')
AVG=$(echo "$PING_ALL" | awk -F'/' '/round-trip/{print $5}')
MDEV=$(echo "$PING_ALL" | awk -F'/' '/round-trip/{print $6}' | sed 's/ ms//')

if [[ -n "$LOSS" && "$LOSS" != "0.0%" ]]; then
  warn "丢包率 $LOSS（>0% 即异常）"
fi
if [[ -n "$MDEV" ]] && python3 -c "import sys; sys.exit(0 if float('$MDEV') > 20 else 1)" 2>/dev/null; then
  warn "抖动 ${MDEV}ms（>20ms 算高）"
fi

hr "[3/3] 路径追踪"
echo "单次 traceroute（8 hops × 1 probe，控制时间）:"
traceroute -m 8 -q 1 -w 2 "$TARGET" 2>&1 | head -12

if [[ -n "$DEEP" ]]; then
  echo ""
  echo "深度模式：3 轮 traceroute 叠加（看路由跳变）"
  for i in 1 2 3; do
    echo "--- 轮 $i ---"
    traceroute -m 8 -q 1 -w 2 "$TARGET" 2>&1 | awk 'NR>1 && $1 !~ /traceroute/ {print $1, $2, $3}'
  done | sort | uniq -c | sort -rn | head -10
else
  echo ""
  echo "深度模式未启用（耗时约 30-60s）。要追路由跳变跑：bash bin/mtr-style.sh $TARGET 3 deep"
fi

printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
printf '• 丢包集中在某一跳 → 那一跳运营商问题（换路径 / 换节点）\n'
printf '• 抖动高 → 跨境或无线（§10 坑清单）\n'
printf '• 路由跳变（deep 模式） → 路由不稳（§5.1）\n'
printf '• 整段都通但目标不通 → 应用层（§7 / §8）\n'