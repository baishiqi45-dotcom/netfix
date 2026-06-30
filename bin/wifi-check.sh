#!/usr/bin/env bash
# wifi-check.sh — Wi-Fi 信号 / 信道 / 物理层
# 对应 final.md §3 Wi-Fi
# 用法：bash bin/wifi-check.sh [--json]

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

AIRPORT="/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
AIRPORT_AVAILABLE=false
[[ -x "$AIRPORT" ]] && AIRPORT_AVAILABLE=true

hr "[1/5] 当前 Wi-Fi 连接状态"
CONN_STATUS="ok"
if [[ "$AIRPORT_AVAILABLE" == true ]]; then
  AIRPORT_INFO=$("$AIRPORT" -I 2>&1 | head -25)
  echo "$AIRPORT_INFO"
  SSID=$(echo "$AIRPORT_INFO" | awk -F': ' '/ SSID/{print $2}' | tr -d ' ')
else
  echo "airport 命令不在 — 改用 networksetup"
  networksetup -getairportnetwork en0 2>&1
  SSID=$(networksetup -getairportnetwork en0 2>/dev/null | awk -F': ' '{print $2}')
fi
add_check "wifi_connection" "$CONN_STATUS" "{\"ssid\":\"$SSID\",\"airport_available\":$AIRPORT_AVAILABLE}"

hr "[2/5] 信号强度读数"
RSSI_STATUS="ok"
RSSI=""
if [[ "$AIRPORT_AVAILABLE" == true ]]; then
  "$AIRPORT" -I 2>/dev/null | awk -F': ' '/agrCtlRSSI|agrCtlNoise/{print}'
  RSSI=$("$AIRPORT" -I 2>/dev/null | awk -F': ' '/agrCtlRSSI/{print $2}' | tr -d ' ')
  if [[ -n "$RSSI" ]]; then
    if [[ "$RSSI" -ge -55 ]]; then
      ok "RSSI=$RSSI dBm（强）"
    elif [[ "$RSSI" -ge -70 ]]; then
      warn "RSSI=$RSSI dBm（中）— 看 §3.1"
      RSSI_STATUS="warn"
    else
      err "RSSI=$RSSI dBm（弱）— 物理层问题 — §3.4 十大原因"
      RSSI_STATUS="fail"
    fi
  fi
else
  echo "跳过（airport 不可用）"
fi
add_check "rssi" "$RSSI_STATUS" "{\"rssi\":\"$RSSI\"}"
update_overall "$RSSI_STATUS"

hr "[3/5] 周边 Wi-Fi 网络扫描（看信道拥挤）"
SCAN_STATUS="ok"
if [[ "$AIRPORT_AVAILABLE" == true ]]; then
  SCAN_OUT=$("$AIRPORT" -s 2>/dev/null | head -20 || true)
  echo "$SCAN_OUT"
  [[ -z "$SCAN_OUT" ]] && SCAN_STATUS="warn"
else
  echo "跳过（airport 不可用）"
fi
add_check "wifi_scan" "$SCAN_STATUS" "{\"airport_available\":$AIRPORT_AVAILABLE}"
update_overall "$SCAN_STATUS"

hr "[4/5] en0 IPv4 / IPv6 状态"
IP_STATUS="ok"
SELF_IP=$(ipconfig getifaddr en0 2>&1 || true)
echo "IPv4: ${SELF_IP:-无}"
if [[ -z "$SELF_IP" ]]; then
  warn "en0 无 IPv4"
  IP_STATUS="warn"
fi
INFO_OUT=$(networksetup -getinfo "Wi-Fi" 2>&1 | head -10 || true)
echo "$INFO_OUT"
add_check "en0_ip" "$IP_STATUS" "{\"ipv4\":\"$SELF_IP\"}"
update_overall "$IP_STATUS"

hr "[5/5] 默认网关 + ping"
GW=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}')
echo "默认网关 = ${GW:-（未找到）}"
GW_PING_STATUS="ok"
if [[ -n "$GW" ]]; then
  if ping -c 3 -W 2 "$GW" >/dev/null 2>&1; then
    ping -c 3 -W 2 "$GW" 2>&1 | tail -5
  else
    err "网关 $GW ping 不通"
    GW_PING_STATUS="fail"
  fi
else
  GW_PING_STATUS="warn"
fi
add_check "gateway_ping" "$GW_PING_STATUS" "{\"gateway\":\"$GW\"}"
update_overall "$GW_PING_STATUS"

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  SUMMARY="Wi-Fi 检查完成"
  case "$OVERALL" in
    ok) SUMMARY="Wi-Fi 物理层正常" ;;
    warn) SUMMARY="Wi-Fi 存在警告（信号/扫描/en0 IP），参考 §3" ;;
    fail) SUMMARY="Wi-Fi 物理层故障或网关不可达，参考 §3.4" ;;
  esac
  emit_report "wifi-check" "$OVERALL" "$SUMMARY"
else
  printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
  printf '• RSSI 弱 → 距离 / 隔墙 → §3.4 物理层十大原因\n'
  printf '• 信号强但慢 → 信道拥挤 / 频段粘在弱 5G → §3.2 / §10.5\n'
  printf '• 满格但网页打不开 → 路由器端问题 / DNS / 上联断 → §3.4 / §2\n'
fi
