#!/usr/bin/env bash
# auth-vs-net.sh — 代理认证失败 vs 真实网络问题快速判断
# 对应 memory: 代理 IP 客户端密码不对 = 全 000（错密码 0.x 秒 RST vs 网络 timeout 3-7 秒）
# 用法：bash bin/auth-vs-net.sh [代理URL] [测试URL]
# 例：bash bin/auth-vs-net.sh socks5://user:pass@127.0.0.1:10808 https://api.ipify.org

set -o pipefail

PROXY="${1:-}"
TEST_URL="${2:-https://api.ipify.org}"

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; }

if [[ -z "$PROXY" ]]; then
  hr "用法"
  echo "bash bin/auth-vs-net.sh <代理URL> [测试URL]"
  echo ""
  echo "代理URL 格式："
  echo "  socks5://user:pass@host:port   (SOCKS5 认证)"
  echo "  socks5h://host:port            (SOCKS5 无认证，DNS 走代理)"
  echo "  http://user:pass@host:port     (HTTP CONNECT 代理)"
  echo ""
  echo "例："
  echo "  bash bin/auth-vs-net.sh socks5://user:pass@127.0.0.1:10808"
  echo "  bash bin/auth-vs-net.sh http://127.0.0.1:7890 https://www.google.com"
  exit 0
fi

hr "[1/4] 测试直连基线（不走代理）"
DIRECT_START=$(date +%s.%N)
DIRECT=$(curl -sS --max-time 10 -w "\nHTTP_CODE=%{http_code} TIME=%{time_total}\n" "$TEST_URL" 2>&1 | tail -3)
DIRECT_END=$(date +%s.%N)
DIRECT_ELAPSED=$(awk -v s="$DIRECT_START" -v e="$DIRECT_END" 'BEGIN{printf "%.2f", e-s}')
echo "耗时: ${DIRECT_ELAPSED}s"
echo "$DIRECT" | head -3

hr "[2/4] 测试代理（带超时计时）"
PROTO=$(echo "$PROXY" | awk -F: '{print $1}')
echo "代理协议: $PROTO"
echo "代理 URL: $PROXY"

START=$(date +%s.%N)
PROXY_RESULT=$(curl -sS --max-time 10 -x "$PROXY" -w "\nHTTP_CODE=%{http_code} TIME=%{time_total}\n" "$TEST_URL" 2>&1)
END=$(date +%s.%N)
ELAPSED=$(awk -v s="$START" -v e="$END" 'BEGIN{printf "%.2f", e-s}')

echo "耗时: ${ELAPSED}s"
echo "结果："
echo "$PROXY_RESULT" | head -5

hr "[3/4] 时间差判定"
echo "代理耗时: ${ELAPSED}s"

# 判定阈值
# < 1.0s + HTTP 200 → 代理正常
# < 1.0s + HTTP 407/000 → 认证失败
# > 3.0s + HTTP 000 → 真网络问题

HTTP_CODE=$(echo "$PROXY_RESULT" | grep "HTTP_CODE=" | awk -F= '{print $2}' | head -1)
[[ -z "$HTTP_CODE" ]] && HTTP_CODE="000"

if [[ "$HTTP_CODE" == "200" ]]; then
  ok "代理返回 200 — 认证 + 网络都没问题"
elif [[ "$HTTP_CODE" == "407" ]]; then
  err "HTTP 407 Proxy Authentication Required — 密码错 / 没设认证"
elif awk -v t="$ELAPSED" 'BEGIN{exit !(t < 1.0)}'; then
  if [[ "$HTTP_CODE" == "000" ]]; then
    err "< 1.0s + HTTP 000 → **认证失败**（密码错 / IP 错 / 端口错）"
    echo "  修法：检查代理客户端密码跟服务商后台是否一致（13 字符也要逐字符对）"
  else
    warn "< 1.0s + HTTP $HTTP_CODE → 可能是协议不匹配（HTTP vs SOCKS5）"
  fi
elif awk -v t="$ELAPSED" 'BEGIN{exit !(t > 3.0)}'; then
  if [[ "$HTTP_CODE" == "000" ]]; then
    err "> 3.0s + HTTP 000 → **真网络问题**（GFW / 路径 / 上联）"
    echo "  修法：换节点 / 换 DNS / 换协议 / 测出口 IP 看是否被识别"
  else
    warn "> 3.0s + HTTP $HTTP_CODE → 服务端慢或被丢包"
  fi
else
  echo "1-3s 之间，HTTP $HTTP_CODE — 不确定，再跑一次"
fi

hr "[4/4] 出口 IP（验证代理是否生效）"
EXT_IP=$(curl -sS --max-time 10 -x "$PROXY" https://api.ipify.org 2>/dev/null || true)
DIRECT_IP=$(curl -sS --max-time 10 https://api.ipify.org 2>/dev/null || true)
echo "直连出口: ${DIRECT_IP:-（直连失败）}"
echo "代理出口: ${EXT_IP:-（代理失败）}"

if [[ -n "$EXT_IP" && -n "$DIRECT_IP" && "$EXT_IP" != "$DIRECT_IP" ]]; then
  ok "代理生效（IP 改变）"
elif [[ "$EXT_IP" == "$DIRECT_IP" ]]; then
  warn "代理没生效（IP 一样）— 客户端没走代理或代理透传"
fi

printf '\n\033[1;36m== 关键判断 ==\033[0m\n'
printf '• 0.x 秒 + 000/407 → 认证失败，改密码\n'
printf '• 3-7 秒 + 000 → 真网络问题，换节点 / 换 DNS\n'
printf '• 1-3 秒 → 不确定，再跑\n'
printf '• 直连通但代理卡 → 客户端配置 / 协议选错\n'