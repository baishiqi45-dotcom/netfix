#!/usr/bin/env bash
# macos-network.sh — macOS 特色网络工具（其他平台无对应）
# 对应 final.md §4.1 macOS 防火墙 / §7.1 系统代理
# 用法：bash bin/macos-network.sh

set -o pipefail

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

hr "[1/7] 所有网络服务列表"
networksetup -listallnetworkservices 2>&1 | grep -v "^$" | head -20

hr "[2/7] 当前网络服务状态（hardware port / IPv4 / router）"
# 通过 default route 的 interface 反查对应的 network service
ACTIVE_IF=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
if [[ -n "$ACTIVE_IF" ]]; then
  echo "默认路由接口: $ACTIVE_IF"
  echo ""
  # 找所有 services 并取第一个 IP 是 192.168/10.* 的（更可能是当前活跃）
  ACTIVE_SVC=""
  while IFS= read -r SVC; do
    [[ "$SVC" =~ ^\*|^\#|^- ]] && continue
    [[ -z "$SVC" ]] && continue
    INFO=$(networksetup -getinfo "$SVC" 2>/dev/null)
    if echo "$INFO" | grep -qE "^IP address: (192\.168\.|10\.|172\.)"; then
      ACTIVE_SVC="$SVC"
      break
    fi
  done < <(networksetup -listallnetworkservices)
  if [[ -z "$ACTIVE_SVC" ]]; then
    ACTIVE_SVC="Wi-Fi"  # fallback
  fi
  echo "活跃服务: $ACTIVE_SVC"
  networksetup -getinfo "$ACTIVE_SVC" 2>&1 | head -10
else
  warn "没找到默认路由"
fi

hr "[3/7] 系统代理（HTTP / HTTPS / SOCKS）"
echo "--- Web Proxy (HTTP) on Wi-Fi ---"
networksetup -getwebproxy Wi-Fi 2>&1
echo "--- Secure Web Proxy (HTTPS) on Wi-Fi ---"
networksetup -getsecurewebproxy Wi-Fi 2>&1
echo "--- SOCKS Proxy on Wi-Fi ---"
networksetup -getsocksfirewallproxy Wi-Fi 2>&1
echo "--- Proxy Auto Config ---"
networksetup -getautoproxyurl 2>&1
networksetup -getproxyautodiscovery 2>&1

# 关键判断：代理开着但 App 不走代理？
PROXY_ON=$(networksetup -getwebproxy Wi-Fi 2>&1 | grep -E "Enabled: Yes" || true)
if [[ -n "$PROXY_ON" ]]; then
  ok "系统 HTTP 代理已开启"
else
  echo "系统 HTTP 代理未开（看上面 scutil --proxy 也行）"
fi

hr "[4/7] 应用层防火墙 socketfilterfw"
APP_FW=$(socketfilterfw --getglobalstate 2>&1)
echo "$APP_FW"
if echo "$APP_FW" | grep -q "enabled"; then
  warn "应用层防火墙开启 — 可能挡某些 App"
  echo "看哪些 App 被挡：socketfilterfw --listapps"
fi

hr "[5/7] pf 包过滤防火墙状态"
PF_STATUS=$(sudo -n pfctl -s info 2>&1 | head -5 || echo "需要 sudo 才能看完整 pf 规则")
echo "$PF_STATUS"
echo ""
echo "当前激活的 rules:"
sudo -n pfctl -s rules 2>&1 | head -10 || warn "需要 sudo"

hr "[6/7] 系统网络日志（最近 5 分钟 DNS 错误）"
# mDNSResponder 是 macOS DNS 进程
log show --predicate 'process == "mDNSResponder"' --last 5m --style compact 2>/dev/null \
  | grep -iE "error|fail|denied|timeout" | head -10 || echo "无 DNS 错误"

hr "[7/7] 系统网络栈详情（system_profiler 摘要）"
system_profiler SPNetworkDataType 2>/dev/null | head -40

printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
printf '• 系统代理开着但 App 不走 → §7.1（部分 App 不读系统代理）\n'
printf '• 防火墙 enabled + App 被拒 → socketfilterfw --add <app>\n'
printf '• pf 规则挡端口 → §4.3 / sudo pfctl -s rules\n'
printf '• DNS 错误日志频繁 → §2 / §10.9 Sonoma 已知问题\n'
printf '• Thunderbolt / USB 网络服务激活但没用 → networksetup -setnetworkserviceenabled off\n'