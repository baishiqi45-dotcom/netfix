#!/bin/bash
# 恢复所有 macOS 网络服务的 IPv6 自动配置。
# 需要以管理员权限运行。
set -euo pipefail

services=$(networksetup -listallnetworkservices | tail -n +2)
if [[ -z "$services" ]]; then
    echo "未找到网络服务" >&2
    exit 1
fi

failed=0
while IFS= read -r service; do
    [[ -z "$service" ]] && continue
    if ! networksetup -setv6automatic "$service"; then
        echo "无法恢复 $service 的 IPv6" >&2
        failed=1
    fi
done <<< "$services"

if [[ $failed -ne 0 ]]; then
    exit 1
fi

echo "已恢复所有网络服务的 IPv6"
