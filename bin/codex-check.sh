#!/usr/bin/env bash
# bin/codex-check.sh — Codex / OpenAI / GitHub reachability quick check
# 用法：bash bin/codex-check.sh [--json]

set -uo pipefail

JSON_MODE=false
if [[ "${1:-}" == "--json" ]]; then
  JSON_MODE=true
fi

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

TIMEOUT=8

probe() {
  local name=$1 proxy=$2 url=$3
  local start end raw rc http_code dur_ms status err

  start=$(date +%s%N)
  if [[ -n "$proxy" ]]; then
    raw=$(curl -sS --max-time "$TIMEOUT" -x "$proxy" -o /dev/null -w "HTTP_CODE=%{http_code}" "$url" 2>&1)
  else
    raw=$(curl -sS --max-time "$TIMEOUT" -o /dev/null -w "HTTP_CODE=%{http_code}" "$url" 2>&1)
  fi
  rc=$?
  end=$(date +%s%N)

  http_code=$(printf '%s' "$raw" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
  http_code=${http_code:-0}
  dur_ms=$(( (end - start) / 1000000 ))

  status="fail"
  err=""
  if [[ $rc -eq 0 && "$http_code" =~ ^2 ]]; then
    status="ok"
  elif [[ $rc -eq 0 ]]; then
    status="warn"
  else
    status="fail"
    err=$(printf '%s' "$raw" | head -1)
  fi

  python3 -c '
import json, sys
name, url, proxy, status, http_code, dur_ms, err = sys.argv[1:8]
if not proxy:
    label = "direct"
elif proxy == "http://127.0.0.1:10808":
    label = "127.0.0.1:10808"
else:
    label = proxy
print(json.dumps({
    "name": name,
    "target": url,
    "proxy": label,
    "status": status,
    "http_code": int(http_code),
    "duration_ms": int(dur_ms),
    "error": err or None,
}, ensure_ascii=False))
' "$name" "$url" "$proxy" "$status" "$http_code" "$dur_ms" "$err"
}

RESULTS=()
RESULTS+=("$(probe "openai_api_direct" "" "https://api.openai.com/v1/models")")
RESULTS+=("$(probe "openai_api_via_10808" "http://127.0.0.1:10808" "https://api.openai.com/v1/models")")
RESULTS+=("$(probe "github_direct" "" "https://github.com")")

if $JSON_MODE; then
  python3 -c '
import json, sys
lines = [json.loads(l) for l in sys.argv[1:] if l.strip()]
def reachable(r):
    return r["status"] != "fail" and r["http_code"] > 0
direct_ok = any(reachable(r) and r["proxy"] == "direct" for r in lines)
proxy_ok = any(reachable(r) and r["proxy"] != "direct" for r in lines)
active = "direct"
for r in lines:
    if reachable(r) and r["proxy"] != "direct":
        active = r["proxy"]
        break
if not direct_ok and not proxy_ok:
    root = "Both direct and proxy access failed; check network/proxy core."
elif not direct_ok and proxy_ok:
    root = "Direct access to Codex/OpenAI/GitHub is blocked; proxy is working."
elif direct_ok and not proxy_ok:
    root = "Direct access works but proxy test failed; check proxy settings."
else:
    root = "Codex/OpenAI/GitHub reachable both directly and via proxy."
print(json.dumps({
    "tests": lines,
    "summary": {"direct_ok": direct_ok, "proxy_ok": proxy_ok, "active_proxy": active, "root_cause": root}
}, ensure_ascii=False, indent=2))
' "${RESULTS[@]}"
else
  hr "Codex / OpenAI / GitHub 可达性"
  for rjson in "${RESULTS[@]}"; do
    python3 -c '
import json, sys
r = json.loads(sys.argv[1])
emoji = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(r["status"], "❓")
name, proxy, code, dur = r["name"], r["proxy"], r["http_code"], r["duration_ms"]
err = r.get("error") or ""
suffix = f" — {err}" if err else ""
print(f"{emoji} {name:<25} proxy={proxy:<20} HTTP {code:>3}  {dur:>5}ms{suffix}")
' "$rjson"
  done

  hr "判定"
  python3 -c '
import json, sys
lines = [json.loads(l) for l in sys.argv[1:]]
def reachable(r):
    return r["status"] != "fail" and r["http_code"] > 0
direct_ok = any(reachable(r) and r["proxy"] == "direct" for r in lines)
proxy_ok = any(reachable(r) and r["proxy"] != "direct" for r in lines)
if direct_ok and proxy_ok:
    print("直连与代理均可用。")
elif proxy_ok:
    print("直连被墙，代理可用。")
elif direct_ok:
    print("直连可用，代理测试失败，检查系统代理 / 10808 端口。")
else:
    print("直连与代理均失败：检查网络、DNS、代理核心是否运行。")
' "${RESULTS[@]}"
fi
