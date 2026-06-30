#!/usr/bin/env bash
# vpn-detect.sh — 自动识别 VPN / 代理客户端类型
# 对应 final.md §1.1 协议选型 / §7.3 代理工具生态
# 用法：bash bin/vpn-detect.sh

set -o pipefail

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }

hr "[1/6] 系统 utun / tun 接口（VPN / WireGuard / IPSec）"
UTUNS=$(ifconfig 2>/dev/null | grep -E "^utun[0-9]+:" | awk '{print $1}' | sed 's/://')
if [[ -z "$UTUNS" ]]; then
  warn "没有 utun 接口 — 没有 VPN 在系统层拨上"
else
  for IF in $UTUNS; do
    IP=$(ifconfig "$IF" 2>/dev/null | awk '/inet /{print $2}' | head -1)
    DESC=$(ifconfig "$IF" 2>/dev/null | awk -F': ' '/description:/{print $2}' | head -1)
    echo "  $IF: $IP ${DESC:+($DESC)}"
  done
fi

hr "[2/6] 系统代理配置（scutil --proxy）"
scutil --proxy 2>&1 | grep -E "Enable|Proxy|Port" | head -15

hr "[3/6] WireGuard（如果 wg 命令存在）"
if command -v wg >/dev/null 2>&1; then
  echo "wg show:"
  sudo -n wg show 2>&1 | head -20 || echo "（需要 sudo）"
else
  echo "wg 不在 PATH — 命令行工具未装 / 用 GUI 客户端"
fi

hr "[4/6] VPN / 代理 GUI / 后端进程识别"
DETECTED=""
# V2RayN / xray / v2ray / sing-box / clash / mihomo / wireguard / surge / shadowrocket / tailscale / trojan / hysteria
PATTERNS=(
  "v2ray|V2RayN / v2ray-core"
  "xray|Xray-core (vless/xtls/reality/vision)"
  "sing-box|Sing-Box"
  "clash|Clash (Verge / Mihomo Party / ClashX / cfw)"
  "mihomo|Mihomo core"
  "wireguard|WireGuard"
  "surge|Surge"
  "shadowrocket|Shadowrocket"
  "tailscale|Tailscale"
  "trojan|Trojan"
  "hysteria|Hysteria"
  "naive|naiveproxy"
  "qv2ray|Qv2Ray"
  "nekobox|NekoBox"
)
for ENTRY in "${PATTERNS[@]}"; do
  PAT=$(printf '%s' "$ENTRY" | cut -d'|' -f1)
  LABEL=$(printf '%s' "$ENTRY" | cut -d'|' -f2)
  if [[ -z "$PAT" || -z "$LABEL" ]]; then continue; fi
  if pgrep -f "$PAT" >/dev/null 2>&1; then
    PID=$(pgrep -f "$PAT" 2>/dev/null | head -1)
    ok "DETECTED: $LABEL (PID $PID)"
    DETECTED="$DETECTED $LABEL"
  fi
done
if [[ -z "$DETECTED" ]]; then
  warn "没识别到已知 VPN/代理 进程 — 可能：1) 没运行 2) 用了小众客户端 3) 只配了 GUI 没启后端"
fi

hr "[5/6] 已知代理端口扫描（看客户端在哪个端口监听）"
# 常见代理端口
PROXY_PORTS=(1080 10808 10809 7890 7891 9090 1087 1089 8388 8889)
for PORT in "${PROXY_PORTS[@]}"; do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -1 | grep -q LISTEN; then
    PROC=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -1 | awk '{print $1}')
    ok "代理端口 $PORT 在监听（$PROC）"
  fi
done

hr "[6/6] 出口 IP（确认代理是否生效）"
EXT_IP=$(curl -sS --max-time 5 https://api.ipify.org 2>/dev/null || true)
echo "当前出口 IP: ${EXT_IP:-（curl 失败）}"
echo "如果显示非本地 ISP IP = 代理生效"

printf '\n\033[1;36m== 结论 ==\033[0m\n'
printf '识别到客户端: %s\n' "${DETECTED:-无}"
printf '下一步: 客户端操作清单见 AGENTS.md §10 GUI 客户端边界\n'