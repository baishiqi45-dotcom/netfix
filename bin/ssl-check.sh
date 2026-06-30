#!/usr/bin/env bash
# ssl-check.sh — SSL/TLS 证书 + 握手检查
# 对应 final.md §8 SSL/TLS
# 用法：bash bin/ssl-check.sh [域名] [--json]

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

hr "[1/5] 系统时间（证书过期最常见根因）"
date
NOW_EPOCH=$(date +%s)
echo "当前 epoch: $NOW_EPOCH"
warn "如果系统时间偏差 > 5 分钟，证书会被判过期 — final.md §8.1"
add_check "system_time" "ok" "{\"epoch\":$NOW_EPOCH}"

hr "[2/5] 证书查看 — openssl s_client"
CERT_STATUS="ok"
CERT_INFO=$(echo | openssl s_client -connect "${TARGET}:443" -servername "${TARGET}" -showcerts 2>&1 | \
  openssl x509 -noout -subject -issuer -dates 2>&1 || true)
echo "$CERT_INFO"
if [[ -z "$CERT_INFO" ]]; then
  err "openssl s_client 拿不到证书 — 握手失败 — final.md §8.2"
  CERT_STATUS="fail"
fi
add_check "certificate" "$CERT_STATUS" "{\"target\":\"$TARGET:443\"}"
update_overall "$CERT_STATUS"

hr "[3/5] 证书链完整性"
CHAIN_STATUS="ok"
CHAIN_OUT=$(echo | openssl s_client -connect "${TARGET}:443" -servername "${TARGET}" 2>&1 | \
  grep -E "Verify return code|verification error" | head -5 || true)
echo "$CHAIN_OUT"
if echo "$CHAIN_OUT" | grep -qE "error|fail|unable"; then
  CHAIN_STATUS="fail"
fi
add_check "cert_chain" "$CHAIN_STATUS" "{\"target\":\"$TARGET:443\"}"
update_overall "$CHAIN_STATUS"

hr "[4/5] 握手是否能完成（短超时）"
HANDSHAKE_STATUS="ok"
HANDSHAKE=$(echo | openssl s_client -connect "${TARGET}:443" -servername "${TARGET}" 2>&1)
if echo "$HANDSHAKE" | grep -q "BEGIN CERTIFICATE"; then
  ok "TLS 握手成功"
elif echo "$HANDSHAKE" | grep -q "Connection refused"; then
  err "连接被拒 — 服务端没开 443 — final.md §5.2"
  HANDSHAKE_STATUS="fail"
elif echo "$HANDSHAKE" | grep -q "Connection timed out\|connect: Connection timed out"; then
  err "连接超时 — 防火墙 DROP — final.md §4.3"
  HANDSHAKE_STATUS="fail"
elif echo "$HANDSHAKE" | grep -q "handshake failure"; then
  err "握手失败 — final.md §8.2 七类根因"
  HANDSHAKE_STATUS="fail"
else
  warn "未知错误 — 看完整输出"
  HANDSHAKE_STATUS="warn"
fi
add_check "handshake" "$HANDSHAKE_STATUS" "{\"target\":\"$TARGET:443\"}"
update_overall "$HANDSHAKE_STATUS"

hr "[5/5] curl 跟证书验证"
CURL_STATUS="ok"
CURL_OUT=$(curl -sS -I --max-time 5 "https://${TARGET}" 2>&1 | head -10 || true)
echo "$CURL_OUT"
if [[ -z "$CURL_OUT" ]]; then
  warn "curl 失败"
  CURL_STATUS="warn"
fi
add_check "curl_verify" "$CURL_STATUS" "{\"url\":\"https://$TARGET\"}"
update_overall "$CURL_STATUS"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  SUMMARY="SSL/TLS 检查完成"
  case "$OVERALL" in
    ok) SUMMARY="TLS 握手与证书验证正常" ;;
    warn) SUMMARY="SSL/TLS 存在警告，请检查系统时间或证书链" ;;
    fail) SUMMARY="SSL/TLS 握手或证书验证失败，参考 §8" ;;
  esac
  emit_report "ssl-check" "$OVERALL" "$SUMMARY"
else
  printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
  printf '• ERR_CERT_DATE_INVALID → 系统时间错（最常见）\n'
  printf '• ERR_CERT_AUTHORITY_INVALID → 自签 / CA 没装（§8.4）\n'
  printf '• handshake failure → §8.2 七类根因\n'
  printf '• SSL_ERROR_SYSCALL → 中间人 / 防火墙拆 TLS — §4.3 / §7\n'
fi
