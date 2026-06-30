#!/usr/bin/env bash
# ipv6-leak-check.sh — 检测 IPv6 泄漏并提供一键关闭
# 对应 final.md §10.2
# 用法：bash bin/ipv6-leak-check.sh [--json]

set -uo pipefail

JSON_MODE=false
for arg in "$@"; do [[ "$arg" == "--json" ]] && JSON_MODE=true; done

HUMAN_LOG=""
if [[ "$JSON_MODE" == true ]]; then
  HUMAN_LOG=$(mktemp)
  exec 3>&1
  exec 1>"$HUMAN_LOG"
  exec 2>>"$HUMAN_LOG"
  trap 'rm -f "$HUMAN_LOG"' EXIT
fi

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

SERVICE="Wi-Fi"

hr "[1/3] 当前 $SERVICE IPv6 状态"
INFO=$(networksetup -getinfo "$SERVICE" 2>&1)
echo "$INFO"

IPV6_ENABLED=false
IPV6_HAS_ADDR=false
if echo "$INFO" | grep -qiE "IPv6:\s*(Automatic|Manual|On)"; then
  IPV6_ENABLED=true
fi
IPV6_ADDR=$(echo "$INFO" | awk -F': ' '/IPv6 IP address/{print $2}' | tr -d ' ')
if [[ -n "$IPV6_ADDR" && "$IPV6_ADDR" != "none" ]]; then
  IPV6_HAS_ADDR=true
fi

IPV6_STATUS="ok"
IPV6_REASON=""
if [[ "$IPV6_ENABLED" == true && "$IPV6_HAS_ADDR" == true ]]; then
  warn "$SERVICE IPv6 已启用并拿到地址 $IPV6_ADDR"
  IPV6_STATUS="warn"
  IPV6_REASON="IPv6 enabled with address $IPV6_ADDR"
elif [[ "$IPV6_ENABLED" == true ]]; then
  warn "$SERVICE IPv6 已启用但未拿到地址"
  IPV6_STATUS="warn"
  IPV6_REASON="IPv6 enabled but no address"
else
  ok "$SERVICE IPv6 已关闭"
  IPV6_REASON="IPv6 disabled"
fi

hr "[2/3] 隧道接口检查（utun 只跑 IPv4 时系统 IPv6 仍活跃 = 泄漏）"
UTUNS=$(ifconfig 2>/dev/null | grep -E "^utun" | awk '{print $1}' | sed 's/://' | tr '\n' ' ')
if [[ -n "$UTUNS" ]]; then
  echo "发现隧道接口: $UTUNS"
else
  echo "未发现 utun 隧道接口"
fi

LEAK_RISK=false
if [[ -n "$UTUNS" && "$IPV6_ENABLED" == true ]]; then
  warn "隧道存在且系统 IPv6 仍活跃 → 存在 IPv6 泄漏风险 — final.md §10.2"
  LEAK_RISK=true
else
  ok "未发现明显 IPv6 泄漏风险"
fi

hr "[3/3] 一键关闭 IPv6（需 sudo）"
DISABLE_CMD="sudo networksetup -setv6off \"$SERVICE\""
echo "命令: $DISABLE_CMD"
echo "执行后将彻底关闭 $SERVICE 的 IPv6，防止 VPN/代理只走 IPv4 时泄漏。"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  python3 -c "
import json,sys
status='warn' if sys.argv[3]=='true' else ('warn' if sys.argv[2]=='true' else 'ok')
checks=[
  {'name':'ipv6_status','status':('warn' if sys.argv[2]=='true' else 'ok'),'details':{'enabled':sys.argv[2]=='true','address':json.loads(sys.argv[5]),'reason':json.loads(sys.argv[6])}},
  {'name':'tunnel_interfaces','status':'ok','details':{'utuns':json.loads(sys.argv[4])}},
  {'name':'leak_risk','status':('warn' if sys.argv[3]=='true' else 'ok'),'details':{'leak_risk':sys.argv[3]=='true'}},
]
result={
  'script':'ipv6-leak-check',
  'status':status,
  'checks':checks,
  'summary':'IPv6 泄漏风险检测完成',
  'manual_steps':[
    {'id':'disable-ipv6','description':'关闭 IPv6 防止泄漏','command':json.loads(sys.argv[7])}
  ]
}
print(json.dumps(result, ensure_ascii=False))
" "$(json_escape "$SERVICE")" "$IPV6_ENABLED" "$LEAK_RISK" "$(json_escape "$UTUNS")" "$(json_escape "$IPV6_ADDR")" "$(json_escape "$IPV6_REASON")" "$(json_escape "$DISABLE_CMD")"
else
  printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
  printf '• VPN 节点只支持 IPv4，但系统 IPv6 仍活跃 → 流量绕过 VPN（§10.2）\n'
  printf '• 修法：%s\n' "$DISABLE_CMD"
  printf '• 验证：重新跑本脚本，确认 IPv6 显示“关闭”\n'
fi
