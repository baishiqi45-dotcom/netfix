#!/usr/bin/env bash
# speedtest.sh — 测速（curl 拉大文件 + 延迟 + 抖动）
# 对应 final.md §5.2 端口测速 / §10 跨境性能
# 用法：bash bin/speedtest.sh  （无参数，跑多源测速点）

set -uo pipefail

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

hr "[1/3] 延迟 + 抖动 + 丢包（ICMP 1.1.1.1，20 包）"
PING_OUT=$(ping -c 20 -W 2 1.1.1.1 2>&1)
echo "$PING_OUT" | tail -3
LOSS=$(echo "$PING_OUT" | awk '/packet loss/{print $7}')
AVG=$(echo "$PING_OUT" | awk -F'/' '/round-trip/{print $5}')
MDEV=$(echo "$PING_OUT" | awk -F'/' '/round-trip/{print $6}' | sed 's/ ms//')
echo "汇总: 延迟 ${AVG:-?} ms | 抖动 ${MDEV:-?} ms | 丢包 ${LOSS:-?}"
if [[ -n "$MDEV" ]] && python3 -c "import sys; sys.exit(0 if float('$MDEV') > 20 else 1)" 2>/dev/null; then
  warn "抖动 ${MDEV}ms > 20ms — 链路不稳"
fi

hr "[2/3] 下载速度（curl 拉 10MB，多测速点）"
# 多个测速点（不依赖单一服务）
SPEED_URLS=(
  "https://speed.cloudflare.com/__down?bytes=10485760"
  "http://speedtest.tele2.net/10MB.zip"
  "https://proof.ovh.net/files/10Mb.dat"
)

for URL in "${SPEED_URLS[@]}"; do
  echo "--- 测速点: $URL ---"
  TMPFILE=$(mktemp)
  START=$(date +%s)
  HTTP_CODE=$(curl -sS -L -o "$TMPFILE" --max-time 15 -w "%{http_code}" -A "Mozilla/5.0" "$URL" 2>/dev/null || echo "000")
  END=$(date +%s)
  SIZE=$(stat -f%z "$TMPFILE" 2>/dev/null || wc -c <"$TMPFILE")
  ELAPSED=$((END - START))
  if [[ $ELAPSED -gt 0 && $SIZE -gt 100000 ]]; then
    SPEED_MBPS=$(python3 -c "print(f'{($SIZE * 8 / 1000000) / $ELAPSED:.2f}')")
    echo "  HTTP $HTTP_CODE | ${SIZE} 字节 | ${ELAPSED} 秒 | ${SPEED_MBPS} Mbps"
  else
    echo "  HTTP $HTTP_CODE | 太小或失败（${SIZE} 字节 / ${ELAPSED} 秒）"
  fi
  rm -f "$TMPFILE"
done

hr "[3/3] 上传速度（跳过，需 speedtest-cli）"
warn "上传测速需要服务端配合，跳过"
echo "如需：brew install speedtest-cli 后跑 speedtest-cli"

printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
printf '• 延迟高 + 丢包 → 路径或跨境问题（§9.2 / §10.3）\n'
printf '• 延迟低 + 下载慢 → 带宽或代理瓶颈（§1.4 MTU / 换节点）\n'
printf '• 延迟低 + 下载快 → 不在网络层，看应用层（§7 代理 / §8 SSL）\n'
printf '• 所有测速点都失败 → 上联断 / 代理挂了 → bin/network-triage.sh\n'