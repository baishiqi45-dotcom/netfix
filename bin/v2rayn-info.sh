#!/usr/bin/env bash
# bin/v2rayn-info.sh — v2rayN running state + active profile + node list
# 用法：bash bin/v2rayn-info.sh [--json]
#
# 安全说明：只读取 IndexId / ConfigType / Address / Port / Remarks，
# 不输出密码 / UUID / ID 等敏感字段。

set -uo pipefail

JSON_MODE=false
if [[ "${1:-}" == "--json" ]]; then
  JSON_MODE=true
fi

V2RAYN_DIR="${HOME}/Library/Application Support/v2rayN"
CONFIG_DIR="${V2RAYN_DIR}/guiConfigs"
CONFIG_FILE="${CONFIG_DIR}/guiNConfig.json"
DB_FILE="${CONFIG_DIR}/guiNDB.db"

running=false
if pgrep -x "v2rayN" >/dev/null 2>&1 || pgrep -i "v2rayn" >/dev/null 2>&1; then
  running=true
fi

active_id=""
if [[ -f "$CONFIG_FILE" ]]; then
  active_id=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("IndexId", ""))' "$CONFIG_FILE" 2>/dev/null || true)
fi

profiles_json="[]"
if [[ -f "$DB_FILE" ]] && command -v sqlite3 >/dev/null 2>&1; then
  profiles_json=$(sqlite3 -separator $'\t' "$DB_FILE" \
    "SELECT IndexId, ConfigType, Address, Port, Remarks FROM ProfileItem;" 2>/dev/null \
    | python3 -c '
import json, sys
rows = []
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line:
        continue
    parts = line.split("\t")
    if len(parts) >= 5:
        rows.append({
            "IndexId": parts[0],
            "ConfigType": int(parts[1]) if parts[1].isdigit() else parts[1],
            "Address": parts[2],
            "Port": int(parts[3]) if parts[3].isdigit() else parts[3],
            "Remarks": parts[4],
        })
print(json.dumps(rows, ensure_ascii=False))
')
fi

if $JSON_MODE; then
  python3 - "$running" "$active_id" "$profiles_json" <<'PY'
import json, sys
running = sys.argv[1] == "true"
active_id = sys.argv[2]
try:
    profiles = json.loads(sys.argv[3])
except Exception:
    profiles = []

active = None
for p in profiles:
    if str(p.get("IndexId")) == str(active_id):
        active = p
        break

print(json.dumps({
    "running": running,
    "config_file": "~/Library/Application Support/v2rayN/guiConfigs/guiNConfig.json",
    "active_profile": active,
    "profiles": profiles,
}, ensure_ascii=False, indent=2))
PY
else
  printf '\n\033[1;36m== v2rayN 状态 ==\033[0m\n'
  if $running; then
    printf '\033[1;32m[ OK ]\033[0m v2rayN 正在运行\n'
  else
    printf '\033[1;33m[WARN]\033[0m v2rayN 未运行\n'
  fi

  echo
  echo "配置文件：${CONFIG_FILE/#${HOME}/~}"
  echo "当前 IndexId：${active_id:-（未读取到）}"

  echo
  echo "节点列表："
  python3 - "$active_id" "$profiles_json" <<'PY'
import json, sys
active_id = sys.argv[1]
try:
    profiles = json.loads(sys.argv[2])
except Exception:
    profiles = []

TYPE_MAP = {1: "vmess", 2: "shadowsocks", 4: "socks", 5: "http", 6: "trojan", 10: "hysteria2"}
for p in profiles:
    marker = " * " if str(p.get("IndexId")) == str(active_id) else "   "
    t = TYPE_MAP.get(p.get("ConfigType"), str(p.get("ConfigType")))
    print(f"{marker}{p.get('Remarks')} [{t}] {p.get('Address')}:{p.get('Port')}")
if not profiles:
    print("  （无节点数据）")
PY
fi
