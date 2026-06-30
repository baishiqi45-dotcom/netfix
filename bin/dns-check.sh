#!/usr/bin/env bash
# dns-check.sh — DNS 全链路检查
# 对应 final.md §2 DNS
# 用法：bash bin/dns-check.sh [域名] [--json]

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

hr "[1/4] 系统 DNS 配置 — scutil --dns"
SCUTIL_STATUS="ok"
SCUTIL_OUT=$(scutil --dns 2>&1 | head -30 || true)
if [[ -z "$SCUTIL_OUT" ]]; then
  warn "scutil 无输出"
  SCUTIL_STATUS="warn"
fi
echo "$SCUTIL_OUT"
add_check "scutil_dns" "$SCUTIL_STATUS" "{\"status\":\"collected\"}"
update_overall "$SCUTIL_STATUS"

hr "[2/4] 解析测试 — dig $TARGET"
LOCAL=$(dig +short +time=3 +tries=1 "$TARGET" 2>/dev/null | head -1)
echo "本地 resolver: ${LOCAL:-（无响应）}"
LOCAL_STATUS="ok"
PUB_RESULTS=()
for NS in 8.8.8.8 1.1.1.1 223.5.5.5; do
  R=$(dig +short +time=3 +tries=1 "$TARGET" @"$NS" 2>/dev/null | head -1)
  echo "@${NS}: ${R:-（无响应）}"
  PUB_RESULTS+=("$NS:$R")
done
LOCAL_DETAILS="{\"target\":\"$TARGET\",\"local\":\"$LOCAL\",\"public\":["
first=true
for pr in "${PUB_RESULTS[@]}"; do
  ns="${pr%%:*}"
  ip="${pr#*:}"
  [[ "$first" == true ]] || LOCAL_DETAILS+=","
  first=false
  LOCAL_DETAILS+="{\"ns\":\"$ns\",\"answer\":\"$ip\"}"
done
LOCAL_DETAILS+="]}"

if [[ -z "$LOCAL" ]]; then
  err "本地解析失败 — final.md §2.2（缓存清理）"
  cat <<'EOF'
  尝试：
    sudo dscacheutil -flushcache
    sudo killall -HUP mDNSResponder
EOF
  LOCAL_STATUS="fail"
else
  ok "本地 DNS 通 ($LOCAL)"
fi
add_check "local_resolve" "$LOCAL_STATUS" "$LOCAL_DETAILS"
update_overall "$LOCAL_STATUS"

hr "[3/4] DoH 旁路检查 — 内网域名"
echo "测 gitlab.internal（典型内网域名）"
INTRA=$(dig +short +time=2 +tries=1 gitlab.internal 2>/dev/null | head -1)
echo "gitlab.internal: ${INTRA:-（无响应，符合预期 — 应在 hosts 或内网 DNS 解析）}"
warn "如果 hosts 配了 gitlab.internal 但浏览器报 NXDOMAIN — final.md §10.1（DoH 旁路 hosts）"
INTRA_STATUS="ok"
[[ -z "$INTRA" ]] && INTRA_STATUS="warn"
add_check "intranet_resolve" "$INTRA_STATUS" "{\"domain\":\"gitlab.internal\",\"answer\":\"$INTRA\"}"
update_overall "$INTRA_STATUS"

hr "[4/4] DNS 缓存状态"
CACHE_OUT=$(dscacheutil -statistics 2>/dev/null | head -10 || true)
echo "$CACHE_OUT"
add_check "dns_cache" "ok" "{\"collected\":true}"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  SUMMARY="DNS 全链路检查完成"
  case "$OVERALL" in
    ok) SUMMARY="DNS 链路正常" ;;
    warn) SUMMARY="DNS 链路存在警告（如内网域名不可解析），请核对 DoH/hosts 配置" ;;
    fail) SUMMARY="DNS 解析失败，建议执行 sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder" ;;
  esac
  emit_report "dns-check" "$OVERALL" "$SUMMARY"
else
  printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
  printf '• 本地挂 / 公共通 → 本地 resolver 问题，flush cache\n'
  printf '• 全部 NXDOMAIN → DNS 污染或配置错（§9.1 大陆环境）\n'
  printf '• 内网域名挂 → DoH 旁路 hosts（§10.1）\n'
fi
