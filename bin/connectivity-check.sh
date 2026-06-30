#!/usr/bin/env bash
# connectivity-check.sh — 端到端连通性（路径 / 端口 / 协议）
# 对应 final.md §5 通用连通性
# 用法：bash bin/connectivity-check.sh [目标] [--json]

set -uo pipefail

JSON_MODE=false
TARGET="example.com"
for arg in "$@"; do
  if [[ "$arg" == "--json" ]]; then
    JSON_MODE=true
  elif [[ "$arg" != -* ]]; then
    TARGET="$arg"
  fi
done

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

hr "[1/5] 解析目标 $TARGET"
IP=$(dig +short +time=3 +tries=1 "$TARGET" 2>/dev/null | head -1)
echo "解析结果: ${IP:-（无响应）}"
RESOLVE_STATUS="ok"
if [[ -z "$IP" ]]; then
  warn "解析失败 — 跳到 bin/dns-check.sh"
  RESOLVE_STATUS="warn"
fi
add_check "resolve" "$RESOLVE_STATUS" "{\"target\":\"$TARGET\",\"ip\":\"$IP\"}"
update_overall "$RESOLVE_STATUS"

hr "[2/5] ping（小包 ICMP）— 含 jitter / 丢包"
PING_STATUS="ok"
PING_OUT=$(ping -c 10 -W 2000 "$TARGET" 2>&1 || true)
echo "$PING_OUT" | tail -3
LOSS=$(echo "$PING_OUT" | awk '/packet loss/{print $7}')
AVG=$(echo "$PING_OUT" | awk -F'/' '/round-trip/{print $5}')
MDEV=$(echo "$PING_OUT" | awk -F'/' '/round-trip/{print $6}' | sed 's/ ms//')
echo ""
echo "汇总: 延迟 ${AVG:-?} ms | 抖动 ${MDEV:-?} ms | 丢包 ${LOSS:-?}"
if [[ -n "$MDEV" ]] && python3 -c "import sys; sys.exit(0 if float('$MDEV') > 20 else 1)" 2>/dev/null; then
  warn "抖动 ${MDEV}ms > 20ms — 链路不稳（§10 / §9.3 运营商）"
  PING_STATUS="warn"
fi
if [[ -n "$LOSS" && "$LOSS" != "0.0%" ]]; then
  err "丢包 $LOSS — 路径问题，跑 bin/mtr-style.sh 看哪一跳"
  PING_STATUS="fail"
fi
add_check "ping" "$PING_STATUS" "{\"target\":\"$TARGET\",\"avg_ms\":\"$AVG\",\"jitter_ms\":\"$MDEV\",\"loss\":\"$LOSS\"}"
update_overall "$PING_STATUS"

hr "[3/5] traceroute 路径（看哪一跳丢包）"
TRACE_STATUS="ok"
TRACE_OUT=$(traceroute -m 8 -q 1 -w 1 "$TARGET" 2>&1 | head -12 || true)
echo "$TRACE_OUT"
[[ -z "$TRACE_OUT" ]] && TRACE_STATUS="warn"
add_check "traceroute" "$TRACE_STATUS" "{\"target\":\"$TARGET\"}"
update_overall "$TRACE_STATUS"

hr "[4/5] 关键端口测速"
PORT_STATUS="ok"
for PORT in 80 443; do
  PORT_CUR="ok"
  if nc -vz -w 3 "$TARGET" "$PORT" >/dev/null 2>&1; then
    ok "TCP $PORT 通"
  else
    RC=$?
    if [[ $RC -eq 124 ]]; then
      err "TCP $PORT 超时 — 防火墙 DROP — final.md §4.3"
      PORT_CUR="fail"
    else
      err "TCP $PORT 拒（连接被拒）— final.md §5.2"
      PORT_CUR="fail"
    fi
  fi
  add_check "tcp_${PORT}" "$PORT_CUR" "{\"target\":\"$TARGET:$PORT\"}"
  if [[ "$PORT_CUR" == "fail" ]]; then PORT_STATUS="fail"; fi
done
update_overall "$PORT_STATUS"

hr "[5/5] HTTP 实测"
HTTP_STATUS="ok"
HTTP_OUT=$(curl -sS -I --max-time 5 "https://${TARGET}" 2>&1 | head -10 || true)
echo "$HTTP_OUT"
if [[ -z "$HTTP_OUT" ]]; then
  warn "HTTPS 失败"
  HTTP_STATUS="warn"
fi
add_check "https" "$HTTP_STATUS" "{\"url\":\"https://$TARGET\"}"
update_overall "$HTTP_STATUS"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  SUMMARY="端到端连通性检查完成"
  case "$OVERALL" in
    ok) SUMMARY="目标 $TARGET 连通性正常" ;;
    warn) SUMMARY="目标 $TARGET 存在抖动/解析/HTTPS 警告，建议跑 mtr-style.sh 深入" ;;
    fail) SUMMARY="目标 $TARGET 存在丢包或端口不通，参考 §5" ;;
  esac
  emit_report "connectivity-check" "$OVERALL" "$SUMMARY"
else
  printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
  printf '• ICMP 通但 TCP 卡 → 防火墙 DROP（§4.3）\n'
  printf '• 某跳丢包 80%%+ → 运营商限速 / 路径问题（§5.1）\n'
  printf '• 80/443 都拒 → 服务端没启 / 上联断\n'
  printf '• HTTP 通 HTTPS 挂 → 证书 / 握手问题（§8）\n'
fi
