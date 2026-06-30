#!/usr/bin/env bash
# process-net.sh — 看哪些进程在用网络
# 对应 final.md §5.4 路由表 / §7.3 代理工具生态
# 用法：bash bin/process-net.sh

set -o pipefail

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

hr "[1/5] 所有 TCP/UDP 监听端口 + 占用进程"
# lsof -iTCP -sTCP:LISTEN + UDP
lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {printf "%-30s %-10s %s\n", $1, $9, $2}' | head -30

hr "[2/5] 已建立的 TCP 连接（ESTABLISHED）"
COUNT=$(lsof -nP -iTCP -sTCP:ESTABLISHED 2>/dev/null | wc -l | tr -d ' ')
echo "活跃连接数: $COUNT"
echo "--- 前 20 条 ---"
lsof -nP -iTCP -sTCP:ESTABLISHED 2>/dev/null | awk 'NR>1 && NR<=21 {printf "%-30s %s\n", $1, $9}' | head -20

hr "[3/5] VPN / 代理相关进程"
echo "查找: v2ray / clash / mihomo / wireguard / surge / shadow / trojan / hysteria / xray / naive"
ps -axo pid,user,command 2>/dev/null | grep -iE "v2ray|clash|mihomo|wireguard|surge|shadow|trojan|hysteria|xray|naive|qv2ray|nekoray" | grep -v grep | head -10 || echo "（未发现运行中的代理客户端）"

hr "[4/5] DNS 相关进程"
ps -axo pid,user,command 2>/dev/null | grep -iE "dns|mdns|dnscrypt|smartdns|dnsmasq|unbound|adguard" | grep -v grep | head -10 || echo "（只有系统 mDNSResponder）"

hr "[5/5] 占带宽 Top 10（实时 5 秒采样）"
echo "采样 5 秒...（用 nettop）"
nettop -P -L 1 -J bytes_in,bytes_out -t wifi 2>/dev/null &
NETTOP_PID=$!
sleep 5
kill -INT $NETTOP_PID 2>/dev/null || true
wait $NETTOP_PID 2>/dev/null || true

printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
printf '• V2RayN / Clash 进程没跑 → 客户端没启动\n'
printf '• 进程在但 0 流量 → §7.3 配置错 / 没选节点\n'
printf '• 大量陌生进程占带宽 → 可能中毒 / 后台程序（nettop 看具体）\n'
printf '• DNS 进程吃 CPU → §2 DNS 配置错或被污染\n'