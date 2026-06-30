#!/usr/bin/env bash
# network-triage.sh — OSI 五层自顶向下分诊
# 对应 final.md §5.5 综合诊断剧本
# 用法：bash bin/network-triage.sh [--json]

set -uo pipefail

JSON_MODE=false
for arg in "$@"; do [[ "$arg" == "--json" ]] && JSON_MODE=true; done

JSON_TMP=""
HUMAN_LOG=""
if [[ "$JSON_MODE" == true ]]; then
  JSON_TMP=$(mktemp)
  HUMAN_LOG=$(mktemp)
  exec 3>&1
  exec 1>"$HUMAN_LOG"
  exec 2>>"$HUMAN_LOG"
  trap 'rm -f "$JSON_TMP" "$HUMAN_LOG"' EXIT
fi

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
add_check() {
  local name="$1" status="$2" details="$3"
  if [[ "$JSON_MODE" == true ]]; then
    printf '{"name":%s,"status":%s,"details":%s}\n' \
      "$(json_escape "$name")" "$(json_escape "$status")" "$details" >> "$JSON_TMP"
  fi
}
emit_report() {
  python3 -c "
import json,sys
checks=[json.loads(l) for l in open('$JSON_TMP').read().splitlines() if l.strip()]
script=sys.argv[1]
status=sys.argv[2]
summary=sys.argv[3]
print(json.dumps({'script':script,'status':status,'checks':checks,'summary':summary}, ensure_ascii=False))
" "$1" "$2" "$3"
}

OVERALL="ok"
update_overall() {
  local s="$1"
  if [[ "$s" == "fail" ]]; then OVERALL="fail"; fi
  if [[ "$s" == "warn" && "$OVERALL" == "ok" ]]; then OVERALL="warn"; fi
}

hr "[1/5] 物理层 — ifconfig / 接口状态"
ifconfig 2>/dev/null | grep -E "^[a-z]|inet |status:" | head -20 || err "ifconfig 无输出"
SELF_IP=$(ipconfig getifaddr en0 2>/dev/null || true)
PHY_STATUS="ok"
PHY_DETAILS="{\"ip\":\"$SELF_IP\"}"
if [[ -z "$SELF_IP" ]]; then
  err "en0 没有 IPv4（DHCP 失败 / 169.254 自分配）— final.md §5.5 物理层"
  PHY_STATUS="fail"
  PHY_DETAILS="{\"ip\":\"\",\"reason\":\"en0 no IPv4\"}"
elif [[ "$SELF_IP" == 169.254.* ]]; then
  warn "en0 拿到 169.254.x.x 自分配地址 — DHCP 没拿到"
  PHY_STATUS="warn"
else
  ok "en0 = $SELF_IP"
fi
add_check "physical_layer" "$PHY_STATUS" "$PHY_DETAILS"
update_overall "$PHY_STATUS"

hr "[2/5] 网关层 — ping 默认网关"
GW=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}')
GW_STATUS="ok"
GW_DETAILS="{\"gateway\":\"$GW\"}"
if [[ -z "$GW" ]]; then
  err "没找到默认网关 — final.md §5.4"
  GW_STATUS="fail"
  GW_DETAILS="{\"gateway\":\"\",\"reason\":\"no default gateway\"}"
else
  echo "默认网关 = $GW"
  if ping -c 3 -W 2 "$GW" >/dev/null 2>&1; then
    ok "网关通"
  else
    err "网关不通 — 物理 / 网线 / Wi-Fi 关联问题 — final.md §5.5 第 2 步"
    GW_STATUS="fail"
    GW_DETAILS="{\"gateway\":\"$GW\",\"reason\":\"ping gateway failed\"}"
  fi
fi
add_check "gateway" "$GW_STATUS" "$GW_DETAILS"
update_overall "$GW_STATUS"

hr "[3/5] DNS 层 — dig example.com"
LOCAL_ANS=$(dig +short +time=3 +tries=1 example.com 2>/dev/null | head -1)
PUB_ANS=$(dig +short +time=3 +tries=1 example.com @8.8.8.8 2>/dev/null | head -1)
echo "本地 DNS 解析: ${LOCAL_ANS:-（无响应）}"
echo "公共 DNS 解析: ${PUB_ANS:-（无响应）}"
DNS_STATUS="ok"
DNS_DETAILS="{\"local\":\"$LOCAL_ANS\",\"public\":\"$PUB_ANS\"}"
if [[ -z "$LOCAL_ANS" && -z "$PUB_ANS" ]]; then
  err "DNS 全挂 — final.md §2（缓存 / DoH 旁路 / 污染）"
  DNS_STATUS="fail"
elif [[ -z "$LOCAL_ANS" && -n "$PUB_ANS" ]]; then
  warn "本地 DNS 挂但公共 DNS 通 — 本地 resolver 问题 — final.md §2.2"
  DNS_STATUS="warn"
elif [[ -n "$LOCAL_ANS" ]]; then
  ok "DNS 通 ($LOCAL_ANS)"
fi
add_check "dns" "$DNS_STATUS" "$DNS_DETAILS"
update_overall "$DNS_STATUS"

hr "[4/5] 路径层 — traceroute 8.8.8.8"
TRACE_STATUS="ok"
TRACE_OUT=$(traceroute -m 8 -w 2 8.8.8.8 2>&1 | head -12 || true)
echo "$TRACE_OUT"
if [[ -z "$TRACE_OUT" ]]; then
  warn "traceroute 无输出"
  TRACE_STATUS="warn"
fi
add_check "traceroute" "$TRACE_STATUS" "{\"target\":\"8.8.8.8\"}"
update_overall "$TRACE_STATUS"

hr "[5/5] 端口层 — nc -vz 8.8.8.8:443 / 80"
PORT443_STATUS="ok"
PORT80_STATUS="ok"
if nc -vz -w 3 8.8.8.8 443 2>&1; then
  ok "443 端口通"
else
  warn "443 端口不通（防火墙 DROP？）— final.md §4.3"
  PORT443_STATUS="warn"
fi
nc -vz -w 3 8.8.8.8 80 2>&1 || true
add_check "port_443" "$PORT443_STATUS" "{\"target\":\"8.8.8.8:443\"}"
add_check "port_80" "$PORT80_STATUS" "{\"target\":\"8.8.8.8:80\"}"
update_overall "$PORT443_STATUS"

hr "[bonus] 多源出口 IP（验证代理是否生效）"
EXIT_IPS=()
IP_STATUS="ok"
for IP_SVC in "https://api.ipify.org" "https://ifconfig.me" "https://ip.sb" "https://api.ip.sb/ip"; do
  R=$(curl -sS --max-time 5 "$IP_SVC" 2>/dev/null | head -c 60)
  echo "${IP_SVC}: ${R:-（无响应）}"
  [[ -n "$R" ]] && EXIT_IPS+=("$R")
done
UNIQUE_COUNT=0
if [[ ${#EXIT_IPS[@]} -gt 0 ]]; then
  UNIQUE_COUNT=$(printf '%s\n' "${EXIT_IPS[@]}" | sort -u | wc -l | tr -d ' ')
  if [[ "$UNIQUE_COUNT" -gt 1 ]]; then
    warn "多家 IP 服务返回不同结果（${UNIQUE_COUNT} 个）— 出口被代理劫持 / DNS 泄漏"
    IP_STATUS="warn"
  fi
fi
add_check "exit_ips" "$IP_STATUS" "{\"count\":${#EXIT_IPS[@]},\"unique\":$UNIQUE_COUNT}"
update_overall "$IP_STATUS"

hr "[bonus] curl --resolve 绕过 DNS 测（验证 DNS 是不是根因）"
BYPASS_STATUS="ok"
BYPASS_DETAIL="skipped"
if [[ -n "${PUB_ANS:-}" ]]; then
  echo "强制 example.com 走 ${PUB_ANS}（绕过本地 DNS）:"
  if curl -sS -o /dev/null --max-time 5 -w "HTTP %{http_code} 耗时 %{time_total}s\n" \
    --resolve "example.com:443:${PUB_ANS}" https://example.com 2>&1; then
    ok "绕 DNS 可通 → DNS 可能是根因"
    BYPASS_DETAIL="bypass-ok"
  else
    warn "绕 DNS 也不通 → 不是 DNS 锅"
    BYPASS_STATUS="warn"
    BYPASS_DETAIL="bypass-fail"
  fi
else
  warn "没有可用 IP，跳过 --resolve 测"
  BYPASS_STATUS="warn"
fi
add_check "dns_bypass" "$BYPASS_STATUS" "{\"result\":\"$BYPASS_DETAIL\"}"
update_overall "$BYPASS_STATUS"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  SUMMARY="OSI 五层分诊完成"
  case "$OVERALL" in
    ok) SUMMARY="OSI 五层分诊通过，基础网络健康" ;;
    warn) SUMMARY="OSI 五层分诊存在警告，建议查看具体检查项" ;;
    fail) SUMMARY="OSI 五层分诊发现故障，请按 final.md §5.5 进一步定位" ;;
  esac
  emit_report "network-triage" "$OVERALL" "$SUMMARY"
else
  printf '\n\033[1;36m== 结论 ==\033[0m\n'
  printf '看哪一层 FAIL / WARN → 对应 final.md §0 症状速查 → 查根因清单\n'
  printf '症状速查表位置：final.md 第 66 行\n'
  printf 'VPN → §1 / DNS → §2 / Wi-Fi → §3 / 防火墙 → §4 / 通用连通性 → §5 / SSH → §6 / 代理 → §7 / SSL → §8\n'
  printf '\n额外工具：speedtest.sh / mtr-style.sh / port-scan.sh / dns-check.sh（按需跑）\n'
fi
