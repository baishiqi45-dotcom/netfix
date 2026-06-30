#!/usr/bin/env bash
# port-scan.sh — 端口扫描（用 python3 替代 macOS nc）
# 对应 final.md §5.2 端口测速
# 用法：bash bin/port-scan.sh [目标]  默认 example.com

set -uo pipefail

TARGET="${1:-example.com}"

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok() { printf '\033[1;32m[ OPEN ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[FILT  ]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[ CLOSE]\033[0m %s\n' "$*"; }

hr "目标: $TARGET"
IP=$(dig +short +time=3 +tries=1 "$TARGET" 2>/dev/null | head -1)
if [[ -z "$IP" ]]; then
  err "解析失败"
  exit 1
fi
echo "IP: $IP"

# macOS nc 对所有端口都返回 success，必须用 python3 准确判断
scan_port() {
  local host=$1 port=$2
  python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
try:
    s.connect(('$host', $port))
    print('open')
    s.close()
except socket.timeout:
    print('filtered')
except ConnectionRefusedError:
    print('closed')
except OSError as e:
    print('closed')
" 2>/dev/null
}

hr "[常用服务端口扫描]"
COMMON_PORTS=(21 22 23 25 53 80 110 143 443 465 587 993 995 1080 1194 1433 1521 3306 3389 4443 5000 5060 51820 5432 5900 6379 8000 8080 8443 8888 9000 9090 9200 27017)
OPEN_PORTS=()
FILT_PORTS=()
for PORT in "${COMMON_PORTS[@]}"; do
  RESULT=$(scan_port "$IP" "$PORT")
  case "$RESULT" in
    open)
      ok "TCP $PORT"
      OPEN_PORTS+=("$PORT")
      ;;
    filtered)
      warn "TCP $PORT（黑洞 = DROP）"
      FILT_PORTS+=("$PORT")
      ;;
  esac
done

hr "[结果统计]"
echo "开放 (${#OPEN_PORTS[@]}): ${OPEN_PORTS[*]:-无}"
echo "黑洞 (${#FILT_PORTS[@]}): ${FILT_PORTS[*]:-无}"

printf '\n\033[1;36m== 根因速查 ==\033[0m\n'
printf '• 80/443 都关 → 服务端没起或上联断（§5.5）\n'
printf '• 黑洞集中 → 防火墙 DROP（§4.3 黑洞）\n'
printf '• 端口都通但服务不可用 → 应用层问题（§6 SSH / §7 代理）\n'
printf '• 端口都开（奇怪） → 你的代理 / VPN 把流量转发了，测的不是真实目标\n'

# 高级选项提示
printf '\n\033[1;36m== 升级路径 ==\033[0m\n'
printf '扫全端口：brew install nmap && nmap -p- --min-rate 1000 %s\n' "$TARGET"