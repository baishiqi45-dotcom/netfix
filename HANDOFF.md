# HANDOFF — 网络仓库升级为可调用 agent 团队

> 写于 2026-06-13 15:55 (Asia/Shanghai)
> 本会话 ID：`mvs_450b0e163a4f4eeeb6a3f8b9c991a00f`
> 工作区：`/Users/qibaishi/Desktop/网络/`

---

## 1. 一句话状态

第一刀交付完成。仓库从"放着 runbook 的空壳子"升级为**真能调用的网络排查 agent 团队**：

- ✅ 主 rein `network-debugger` 已注册到 mavis daemon
- ✅ 6 个可执行 bin 脚本（macOS 优先），全部实测跑通
- ✅ AGENTS.md 入口文档就位
- ⏸ 第二刀（subagent 分流）等真 case 触发再决定

**用户的下一动作**：跟 mavis 对话里说"网络坏了"，main agent 会识别并 dispatch 到 network-debugger；或者直接 `bash bin/network-triage.sh` 看健康度。

---

## 2. 已交付

| 产物 | 路径 | 状态 |
|------|------|------|
| 主 rein（仓库） | `.harness/reins/network-debugger/agent.md` | ✅ 171 行 |
| 主 rein（daemon） | `~/.mavis/agents/network-debugger/agent.md` | ✅ 已同步 |
| daemon 注册 | `mavis agent list` 可见 `network-debugger` (source=global) | ✅ |
| 仓库入口 | `AGENTS.md` | ✅ |
| OSI 五层分诊 | `bin/network-triage.sh` | ✅ 实测通 |
| DNS 检查 | `bin/dns-check.sh` | ✅ 实测通 |
| VPN / 隧道 | `bin/vpn-check.sh` | ✅ 实测通（看到 utun54 + 10808 代理） |
| Wi-Fi 检查 | `bin/wifi-check.sh` | ✅ 实测通 |
| SSL/TLS | `bin/ssl-check.sh` | ✅ 实测通（证书 OK） |
| 端到端连通性 | `bin/connectivity-check.sh` | ✅ 实测通 |
| Runbook（已有） | `final.md` | ✅ 1545 行 / 8 大类 + 13 gotchas |
| 研究素材（已有） | `document.md` | ✅ 1732 行 |

**实测 baseline（2026-06-13 15:04-15:06）**：
- en0 = 192.168.0.102（DHCP 正常）
- 默认网关 192.168.0.1 通
- DNS 通（example.com → 104.20.23.154）
- TCP 443/80 都通
- TLS 握手成功（Cloudflare TLS Issuing ECC CA 3）
- 出口 IP 63.124.160.52（用户当前走 V2RayN 10808 代理）

---

## 3. 未做（保留）

| 项 | 原因 | 触发条件 |
|----|------|----------|
| `vpn-specialist` / `dns-specialist` / `wifi-specialist` / `ssl-specialist` subagent | 第一刀先做单 rein 多面手，症状分流在内部走 | 用户实测时症状明显按 4 类分，再建专项 |
| `bin/*.sh` 可执行位 | 全局权限规则卡 chmod（allowAlways 也不生效），用 `bash xxx.sh` 绕过 | 用户自己 chmod 或重写规则 |
| 真 case 沉淀到 `runbook-cases/` | 仓库无历史 case | 用户触发诊断后再说 |
| mavis hook / cron 自动体检 | 第二/三刀范围 | 用户拍板后 |
| 重写 daemon system-prompt | `mavis agent update --system-prompt` 命令存在但 171 行传命令行可能截断 | 用户实测发现 system prompt 不全时 |

---

## 4. 第二刀建议（等用户拍板）

1. **真 case 喂出分流**：用户触发 2-3 次不同症状后，看症状分布决定要不要拆 subagent
2. **case 沉淀目录**：建 `runbook-cases/<日期>-<症状>.md`，agent 修好后提议写入
3. **mavis cron 定时体检**：`mavis cron self network-weekly-check --every 168h --prompt "bash bin/network-triage.sh"` 每周自动跑一次
4. **Hook 自动触发**：每次 `ping 8.8.8.8` 失败自动起 triage（mavis hook）

**所有第二刀都等用户拍板**，agent 不主动建文件。

---

## 5. 验证 / 验收命令

```bash
# 1. daemon 视角
mavis agent list --human | grep network-debugger
# 预期：network-debugger  global   Network Debugger     custom

# 2. 项目视角（--project filter）
mavis agent list --project /Users/qibaishi/Desktop/网络 --human
# 预期：看到 network-debugger（source=global，但 filter 命中因 daemon 默认加上 session workspaceDir）

# 3. 仓库结构
ls /Users/qibaishi/Desktop/网络/
# 预期：AGENTS.md  HANDOFF.md  document.md  final.md  bin/  .harness/  .opencode/

ls /Users/qibaishi/Desktop/网络/bin/
# 预期：6 个 .sh 文件

# 4. 脚本实测（任一）
bash /Users/qibaishi/Desktop/网络/bin/network-triage.sh
bash /Users/qibaishi/Desktop/网络/bin/dns-check.sh
bash /Users/qibaishi/Desktop/网络/bin/vpn-check.sh
bash /Users/qibaishi/Desktop/网络/bin/wifi-check.sh
bash /Users/qibaishi/Desktop/网络/bin/ssl-check.sh
bash /Users/qibaishi/Desktop/网络/bin/connectivity-check.sh [目标域名]
```

---

## 6. 真假状态

### 已验证 ✅
- 6 个 bin 脚本全部跑通（用户机器当前网络健康）
- daemon 注册 `network-debugger` 成功
- daemon 目录 agent.md 已同步

### 推断 ⚠️
- 用户真实环境是 macOS + V2RayN（基于脚本输出 10808 端口代理 + HANDOFF 历史）
- mavis system-prompt 加载：agent.md 文件已写，但 daemon 是否把文件内容加载到 system-prompt 还需 `mavis agent info network-debugger` 验证

### 未验证 ❓
- 用户实测时 main agent 是否真的 dispatch 到 network-debugger
- bin 脚本在断网场景下的表现（baseline 是健康的）

---

## 7. 上一会话的判断、复盘、纠错（沉淀，避免重蹈）

### 我自己（mavis）犯过的错
1. **没问就猜客户端类型**——看到 mihomo 类客户端的截图就当 sing-box GUI 写操作指南，被用户当场打回（实际是 V2RayN）
2. **过度解读现象**——那次"代理全炸"推测"平台层被针对"，但用户没切换节点、自己就好了，就是普通单节点抽风
3. **把交付物当终点**——上一轮把 final.md 落盘就汇报，被打回"报告不是工具"

### 本会话遵循的修正
- 操作任何客户端 / 服务前，**先问是什么**
- 用户说"正常 / 恢复了"——就接受，不深挖
- 任何工作完成时，**先想"这是不是用户要的'工具'"**——不是文档

---

## 8. 立即可用的实测入口

```bash
# 测试 daemon agent 加载
mavis agent info network-debugger 2>&1 | head -20

# 跑全套 baseline（30-60 秒）
bash /Users/qibaishi/Desktop/网络/bin/network-triage.sh

# 单独测 DNS
bash /Users/qibaishi/Desktop/网络/bin/dns-check.sh

# 跟 mavis main agent 说话触发 dispatch
# "网络坏了" / "VPN 连不上" / "DNS 解析失败" 任意一句
```