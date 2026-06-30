#!/usr/bin/env bash
# bin/mihomo-api-check.sh — mihomo / Clash External Controller API check
# 用法：bash bin/mihomo-api-check.sh [PORT] [--json]

set -uo pipefail

PORT="${1:-9090}"
JSON_MODE=false

# Handle both orderings: "--json" and "9090 --json"
if [[ "$PORT" == "--json" ]]; then
  JSON_MODE=true
  PORT="${2:-9090}"
elif [[ "${2:-}" == "--json" ]]; then
  JSON_MODE=true
fi

BASE="http://127.0.0.1:${PORT}"

VERSION_OUT=$(curl -sS --max-time 3 "${BASE}/version" 2>&1 || true)
VERSION_CODE=$?
PROXIES_OUT=$(curl -sS --max-time 3 "${BASE}/proxies" 2>&1 || true)
PROXIES_CODE=$?
GLOBAL_OUT=$(curl -sS --max-time 3 "${BASE}/proxies/GLOBAL" 2>&1 || true)

if $JSON_MODE; then
  python3 - "$VERSION_OUT" "$PROXIES_OUT" "$GLOBAL_OUT" "$PORT" "$VERSION_CODE" "$PROXIES_CODE" <<'PY'
import json, sys
v_raw, p_raw, g_raw, port, v_code, p_code = sys.argv[1:7]

reachable = False
version = None
now = None
proxies = []

try:
    v = json.loads(v_raw)
    reachable = True
    version = v.get("version")
except Exception:
    pass

try:
    p = json.loads(p_raw)
    proxies = sorted(p.get("proxies", {}).keys())
except Exception:
    pass

try:
    g = json.loads(g_raw)
    now = g.get("now")
except Exception:
    pass

print(json.dumps({
    "port": int(port),
    "reachable": reachable,
    "version": version,
    "active_proxy": now,
    "proxies": proxies,
}, ensure_ascii=False, indent=2))
PY
else
  printf '\n\033[1;36m== mihomo / Clash API 检查 (%s) ==\033[0m\n' "$BASE"

  if [[ $VERSION_CODE -eq 0 ]] && echo "$VERSION_OUT" | head -1 | grep -q '{'; then
    printf '\033[1;32m[ OK ]\033[0m API 可达\n'
    echo "$VERSION_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"  version: {d.get(\"version\")}")'
  else
    printf '\033[1;31m[FAIL]\033[0m API 不可达（端口 %s 无响应）\n' "$PORT"
  fi

  echo
  echo "当前活动代理："
  echo "$GLOBAL_OUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    now = d.get("now", "(未知)")
    print(f"  {now}")
except Exception:
    print("  (无法解析)")
'

  echo
  echo "代理列表："
  echo "$PROXIES_OUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for name in sorted(d.get("proxies", {}).keys()):
        print(f"  - {name}")
except Exception:
    print("  (无法解析)")
'

fi
