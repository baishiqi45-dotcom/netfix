#!/usr/bin/env bash
# mtu-tune.sh — 探测最大不分片包并推荐 MTU
# 对应 final.md §1.4 / §10.3
# 用法：bash bin/mtu-tune.sh [目标] [--json]   默认目标 8.8.8.8

set -uo pipefail

JSON_MODE=false
TARGET="8.8.8.8"
for arg in "$@"; do
  if [[ "$arg" == "--json" ]]; then
    JSON_MODE=true
  elif [[ "$arg" != -* ]]; then
    TARGET="$arg"
  fi
done

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

hr "MTU 探测目标: $TARGET"

# macOS ping -D (don't fragment) -s sets payload bytes; total = payload + 28
LO=0
HI=1472
BEST=0
PROBES=()

while [[ $LO -le $HI ]]; do
  MID=$(( (LO + HI) / 2 ))
  [[ "$MID" -lt 0 ]] && MID=0
  if ping -D -s "$MID" -c 1 -W 2 "$TARGET" >/dev/null 2>&1; then
    BEST=$MID
    LO=$((MID + 1))
  else
    HI=$((MID - 1))
  fi
  PROBES+=("$MID")
done

RECOMMENDED=$((BEST + 28))

if [[ "$JSON_MODE" == true ]]; then
  exec 1>&3
  python3 -c "
import json,sys
probes=[int(x) for x in json.loads(sys.argv[4]).split(',') if x]
status='ok' if $BEST>0 else 'fail'
result={
  'script':'mtu-tune',
  'status':status,
  'checks':[{'name':'mtu_probe','status':status,'details':{'target':json.loads(sys.argv[1]),'max_payload':$BEST,'recommended_mtu':$RECOMMENDED,'probes':probes}}],
  'summary':f'最大不分片 payload={$BEST} bytes, 推荐 MTU={$RECOMMENDED} (目标 '+json.loads(sys.argv[1])+')'
}
print(json.dumps(result, ensure_ascii=False))
" "$(json_escape "$TARGET")" "$BEST" "$RECOMMENDED" "$(json_escape "$(printf '%s,' "${PROBES[@]}")")"
else
  echo "探测次数: ${#PROBES[@]}"
  if [[ $BEST -eq 0 ]]; then
    err "无法找到可用 payload（目标可能禁 ICMP 或路径 MTU 极小）"
  else
    ok "最大不分片 payload = $BEST bytes"
    echo "推荐 MTU = $RECOMMENDED (payload + 28 byte IP/ICMP 头)"
    echo ""
    echo "常见参考值："
    echo "  1500 — 以太网默认"
    echo "  1492 — PPPoE"
    echo "  1420 — WireGuard 默认"
    echo ""
    echo "如需应用到 WireGuard，在 [Interface] 加："
    echo "  MTU = $RECOMMENDED"
  fi
fi
