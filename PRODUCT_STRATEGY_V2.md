# netfix 产品战略升级方案 V2

> 版本：v2.0（在 v0.1 战略与 v0.2 技术原型基础上的全面升级）  
> 定位：把 netfix 从「AI 服务能否访问」升级为**全栈网络/代理自愈诊断专家**。  
> 目标：让小白用户能点一下就知道「为什么上不去网」，让高级用户/Agent 能透视住宅 IP、上游 IP、中转、协议、IPv4/IPv6、Wi-Fi、认证等完整链路。

---

## 1. 核心判断：为什么要升级

### 1.1 当前问题

v0.2 的 netfix 已经能：
- 检测常见 AI 服务是否可达；
- 给出基于规则的建议；
- 通过 MCP/API 被 Agent 调用；
- 跑出一个原生 SwiftUI App。

但它仍然是**以目标服务为中心**的「ping 工具」：告诉用户 ChatGPT 能不能打开，却对「为什么打不开」解释得不够深。

### 1.2 用户真实诉求（来自反复反馈）

- 不只是 OpenAI，还要覆盖 YouTube、Twitter、Telegram、Cursor、GitHub、Google 等所有海外服务。
- 不只是「通/不通」，还要知道：
  - 是 Wi-Fi 不行，还是 DHCP 没拿到 DNS？
  - 是代理协议/端口配错了，还是账号密码失效？
  - 是住宅 IP 被风控，还是上游 IP 被拉黑？
  - 是 DNS 泄漏，还是 IPv6 泄漏？
  - 是中转节点炸了，还是本地 SOCKS/HTTP 混淆？
- 用**人话**讲清楚，并给出一键修复按钮。
- 让 AI Agent 能拿到完整上下文，不再靠用户截图猜配置。

### 1.3 升级后的定位

> netfix = **macOS 原生网络自愈层**：不替代 Clash/Surge/v2rayN，而是站在它们之上，把「网络为什么坏、坏在哪一层、怎么修」解释明白并自动修复。

---

## 2. 扩展版网络栈诊断分类（Layer Taxonomy）

把诊断从「目标服务可达」扩展到 OSI 全栈，逐层定位根因。

| 层级 | 检查项 | 关键问题 | 代表命令/API |
|---|---|---|---|
| **L1 物理 / Wi-Fi** | 是否连上 AP、信号强度、噪声、信道、BSSID | 电脑真的连上网了吗？ | `wdutil info`、`CoreWLAN`、`networksetup -getairportnetwork en0` |
| **L2 链路 / DHCP** | IP 地址、子网、网关、DNS、租约 | DHCP 给到的配置对吗？ | `ipconfig getpacket en0`、`ipconfig getoption en0 router`、`scutil --nwi` |
| **L3 网关 / 路由 / IPv4/IPv6** | 默认路由、IPv6 路由、网关可达、地址族偏好 | 流量能走出去吗？IPv6 是否绕过代理？ | `route -n get default`、`netstat -rn -f inet6`、`ping6 2606:4700:4700::1111` |
| **L4 TCP/UDP 连通性** | 端口可达、SYN/RST、握手时间 | 到代理/目标的三次握手成功吗？ | `nc -zv`、`lsof -i -P -n` |
| **L5/L7 代理协议** | HTTP/SOCKS5 是否启用、协议是否正确、认证是否通过、PAC 是否生效 | 代理客户端 listen 了吗？系统代理指向正确吗？账号密码对吗？ | `networksetup -getwebproxy Wi-Fi`、`scutil --proxy`、curl `-x`/`--socks5-hostname` |
| **出口身份 / IP 情报** | 公网 IPv4/IPv6、ISP/ASN、住宅/数据中心、风险评分 | 外界看到的 IP 是什么？会不会被目标站拉黑？ | `https://api.ip.sb/ip`、`ipinfo.io`、`ip-api.com`、`ipapi.is`、AbuseIPDB、proxycheck.io |
| **DNS 解析 / 泄漏** | 当前解析器、解析结果、DNS 泄漏、DoH/DoT | DNS 是否走代理？有没有泄漏真实位置？ | `scutil --dns`、`dig @1.1.1.1`、ipleak.net、dnsleaktest.com |
| **TLS / 证书 / 指纹** | 证书链、JA3/JA4 TLS 指纹、MITM 证书 | 是否被中间人/企业防火墙拦截？指纹是否像机器人？ | `openssl s_client -connect`、`https://tls.peet.ws/api/all` |
| **上游 / 中转 / 路径** | 每一跳延迟/丢包、链路拥堵、中转是否炸 | 瓶颈在本地、ISP、中转，还是出口？ | `mtr`、`traceroute`、`nexttrace`、`networkQuality` |
| **目标服务 / 风控** | HTTP 状态码、地区/账号限制、API 返回 | 是目标服务本身挂了，还是用户被风控？ | 直接 probe 目标 URL，解析错误码 |

### 2.1 每层的关键判定信号

| 层级 | 红色信号 | 黄色信号 | 绿色信号 |
|---|---|---|---|
| Wi-Fi | RSSI < -75 dBm、无关联 AP | RSSI -65 ~ -75、信道拥挤 | RSSI > -50、速率接近 PHY 上限 |
| DHCP | 169.254.x.x、无 router/DNS 选项 | 租约短、DNS 异常 | 正常私网 IP、网关/DNS 齐全 |
| 网关 | 默认路由缺失、ping 不通网关 | 网关可达但外网延迟高 | 网关+外网均正常 |
| IPv6 | 仅有 link-local、IPv6 默认路由丢失 | IPv6 出口与 IPv4 不一致 | IPv4/IPv6 都通且一致 |
| 代理协议 | 系统代理指向未监听端口、407 认证失败 | PAC 返回错误、SOCKS 误用 socks5:// | 代理 listen、认证通过、socks5h 使用正确 |
| IP 情报 | 数据中心/滥用 IP、风险分高 | ISP 代理、ASN 被风控 | 住宅/移动 IP、风险分低 |
| DNS | 本地 DNS 与代理 DNS 不一致、解析超时 | DNS over HTTPS 配置异常 | 解析快、无泄漏、走代理侧 |
| TLS/指纹 | 自签名证书、JA3 被标记为 bot | 企业根证书存在 | 证书链完整、指纹正常 |
| 路径 | 第一跳丢包严重 | 中间某跳延迟突增 | 端到端稳定、延迟合理 |
| 目标服务 | 403/451/429、SSL 错误 | 部分地区慢 | 200/正常响应 |

---

## 3. 用户场景与故障模式

### 3.1 小白用户场景

| 用户原话 | 可能根因 | netfix 应给出的结论 |
|---|---|---|
| "我打开 ChatGPT 一直在转圈" | Wi-Fi 信号差 / DNS 解析慢 / 代理没开 | "当前 Wi-Fi 信号较弱，或者代理客户端没有启动" |
| "为什么手机能上，Mac 不行" | Mac 系统代理没配 / IPv6 泄漏 / DNS 不同 | "Mac 没有使用代理，而手机已经在用梯子" |
| "换了节点就好了" | 旧节点 IP 被目标站风控 | "上一个出口 IP 被 OpenAI 风控，换节点后正常" |
| "点了一键修复还是上不去" | 根因是账号失效/上游炸/IPv6 泄漏，不在一键修复范围内 | "检测到 SOCKS 代理需要账号密码，请先检查代理客户端" |
| "App 提示网络错误，但浏览器可以" | CLI/App 没继承系统代理 / QUIC 绕过 | "你的命令行工具没有走系统代理，建议设置环境变量" |

### 3.2 高级用户场景

| 场景 | 技术根因 | netfix 应输出 |
|---|---|---|
| 自建 v2ray/xray 节点，部分网站 403 | 出口 IP 是数据中心 ASN / IP 被滥用 | "出口 IP 属于 Hetzner 数据中心，且 AbuseIPDB 风险分 82，建议换住宅 IP" |
| 使用 中转 机场，晚上特别卡 | 中转节点 QoS 或国际出口拥堵 | "第一跳到机场入口正常，但第 8 跳（洛杉矶）丢包 30%，建议换入口/出口" |
| HTTP 代理正常，SOCKS5 不行 | 客户端只开了 HTTP inbound，或 Python 缺 PySocks | "系统 SOCKS 代理指向 127.0.0.1:10808，但该端口未监听；请使用 mixed 端口 10808 或开启 SOCKS" |
| 使用 `socks5://` 代理后仍被追踪 | DNS 走本地，泄漏真实位置 | "你配置了 socks5://，DNS 仍走本地；请改用 socks5h:// 或让客户端处理 DNS" |
| 企业/学校网络需要账号密码 | 407 Proxy Authentication Required | "网络代理要求输入用户名密码，请在系统设置 → 网络 → 代理中补全" |
| 开了全局仍被风控 | TLS 指纹是 Python-requests / 浏览器指纹异常 | "当前客户端 JA3 指纹与常见浏览器不一致，容易被反爬/风控" |
| IPv6 能解析但走不通 | macOS IPv6 默认路由丢失 / 代理未 tunnel IPv6 | "IPv6 有地址但无默认路由，ChatGPT 的 AAAA 记录走 IPv6 失败；建议禁用 IPv6 或修复代理 IPv6" |

### 3.3 关键协议差异与陷阱

| 协议 | DNS 行为 | 常见错误 | netfix 建议 |
|---|---|---|---|
| `http://` 代理 | 代理解析 | 企业代理需要 NTLM/Basic 认证 | 检测 407，提示补全账号 |
| `socks5://` | **本地解析**（易泄漏） | 用户以为走了代理，实际 DNS 裸奔 | 改用 `socks5h://` 或客户端 DNS |
| `socks5h://` | 代理解析 | 端口未开或只支持 HTTP | 检测端口监听并提示 |
| `https://` 代理 | 代理解析 | 本地不信任代理 CA | 提示证书问题 |
| PAC/WPAD | 按 URL 选择代理 | PAC 文件错误/本地无法访问 wpad | 评估 PAC 返回值并提示 |

---

## 4. 数据采集与权限模型

### 4.1 核心原则

> **采集拓扑，不采集秘密。**

- 只读取诊断所必需的元数据（端口、模式、规则数、接口状态）。
- 密码、UUID、Token、订阅 URL、私钥必须**本地读取、即时脱敏、不离开本机**。
- 任何数据上传前必须得到用户**明确同意**。

### 4.2 数据来源与脱敏策略

| 数据 | 是否需要权限 | 采集方式 | 脱敏/限制 |
|---|---|---|---|
| 系统代理设置 | 无需额外权限 | `SCDynamicStoreCopyProxies` / `scutil --proxy` / `networksetup` | 只返回启用状态、地址、端口；URL 中的密码替换为 `***` |
| DNS 解析器 | 无需额外权限 | `scutil --dns` | 只返回 DNS IP 与搜索域 |
| 接口/路由 | 无需额外权限 | `NWPathMonitor`、`route`、`netstat`、`ifconfig` | 不收集 MAC 除非必要 |
| Wi-Fi 信号 | 无需额外权限（BSSID 需 Location + WiFi entitlement） | `CoreWLAN`、`wdutil info` | 不收集 BSSID 除非用户授权位置 |
| DHCP 租约 | 无需额外权限 | `ipconfig getpacket en0` | 正常网络参数，不含隐私 |
| 代理客户端配置 | **需要 Full Disk Access 或用户手动选择** | 解析 `~/.config/clash/`、`~/Library/Application Support/Surge/` 等 | 只提取端口、模式、规则数、本地监听；服务器/IP/密码/UUID 全部脱敏 |
| 本地监听端口 | 无需额外权限 | `lsof -i -P -n` | 只返回本机进程与端口 |
| 外部 IP/ASN | 无需权限，但涉及个人数据 | 调用 ipinfo.io / ip-api.com / ip.sb 等 | 缓存结果，不关联用户身份 |
| 信誉查询 | 用户可关闭 | 调用 AbuseIPDB / proxycheck.io 等 | 只读查询，不提交举报 |

### 4.3 权限请求 UX

1. **首次启动**：默认只做「零权限基线诊断」（系统代理、DNS、接口、路由、Wi-Fi、外部 IP）。
2. **高级诊断按钮**：当需要读取 Clash/Surge/v2rayN 配置时，弹出说明：
   > "netfix 需要读取本地代理客户端配置以判断端口/模式是否正确。我们不会读取密码、订阅链接或服务器地址。"
3. **Full Disk Access 引导**：提供截图指引系统设置 → 隐私与安全 → 完整磁盘访问权限 → 添加 netfix。
4. **权限可随时撤回**：设置页显示已授权项，并提供「重新扫描」「删除本地缓存」按钮。

### 4.4 隐私合规要点

- 将 IP 地址视为个人数据；提供隐私政策说明收集目的与保留时间。
- 默认所有诊断本地完成，外部 API 调用需用户知情（首次诊断时提示）。
- 不上传任何代理配置原始内容；导出报告为脱敏 JSON/YAML。
- 如以后做服务器端日志，需支持 GDPR/CCPA 数据主体请求。

---

## 5. 人话解释引擎（Plain-Language Engine）

### 5.1 目标

把技术结果转化为用户能听懂、能行动的结论：
- **一句话结论**："你的 Wi-Fi 信号太弱，导致 ChatGPT 一直转圈。"
- **2-3 句解释**："Mac 虽然连上了路由器，但信号只有 -73 dBm，每 10 个数据包要重发 2 个。"
- **下一步按钮**："移到离路由器更近的位置" 或 "切换到 5GHz 频段"。
- **高级详情（可展开）**：原始命令、指标、阈值。

### 5.2 解释模型：四段式卡片

```
┌─────────────────────────────────────┐
│ 🔴 当前网络不稳定，ChatGPT 可能打不开   │  ← Headline
├─────────────────────────────────────┤
│ 原因：Wi-Fi 信号较弱（-72 dBm），     │  ← Explanation
│ 数据包重传率约 12%。                 │
├─────────────────────────────────────┤
│ [ 移近路由器 ] [ 重启 Wi-Fi ]        │  ← Primary Actions
├─────────────────────────────────────┤
│ ▶ 查看技术详情                       │  ← Expandable
│   RSSI: -72 dBm, Noise: -88 dBm     │
│   丢包: 12%, 网关: 192.168.1.1      │
└─────────────────────────────────────┘
```

### 5.3 典型故障到人话映射

| 技术发现 | 人话结论 | 建议动作 |
|---|---|---|
| DHCP 无 router 选项 | "路由器没有给你正确的上网地址" | 续租 DHCP 或重启路由器 |
| DNS 解析超时，但 `@8.8.8.8` 正常 | "你当前的 DNS 服务器坏了，换个公共 DNS 就好" | 设置 1.1.1.1 / 8.8.8.8 |
| IPv4 通、IPv6 不通，目标有 AAAA | "你的梯子只接管了 IPv4，IPv6 在裸奔" | 禁用 IPv6 或换支持 IPv6 的节点 |
| 系统 HTTP 代理指向未监听端口 | "系统代理设置了一个没有服务的端口" | 检查代理客户端是否启动，或关闭系统代理 |
| 代理返回 407 | "网络代理要求输入账号密码" | 去系统设置补全账号密码 |
| 出口 IP 被 AbuseIPDB 标为高风险 | "你当前出口 IP 被列入风险名单，容易被网站拦截" | 换节点/换住宅 IP |
| 中间某跳丢包但目标正常 | "某个网络中转点压力大，但你访问的目标没问题" | 可观察，若持续严重联系 ISP |
| JA3 指纹像 Python-requests | "你的请求看起来不像普通浏览器，容易被风控" | 使用浏览器或 curl-impersonate |

### 5.4 解释引擎架构

```
观测层（收集原始指标）
   ↓
推理层（决策树 + 置信度评分）
   ↓
叙事层（根据用户等级生成 headline/explanation/detail）
   ↓
动作层（推荐最小可执行下一步）
```

- **观测层**：结构化记录每个层级的结果（布尔、数值、文本、时间戳）。
- **推理层**：规则 + 简单评分，例如「DHCP 无 router → 高置信度本地网络问题」「中间跳丢包但终点正常 → 低置信度，可能只是 ICMP 限速」。
- **叙事层**：根据用户选择的「小白/进阶/专家」模式生成不同颗粒度文案。
- **动作层**：每个结论必须绑定一个可点击按钮或命令；危险操作需要二次确认。

---

## 6. Agent / MCP 集成设计

### 6.1 目标

让 Kimi/Codex/Claude 等 Agent 能**安全、完整、精确**地拿到用户网络状态，从而：
- 不再让用户截图；
- 不被"我网络好像有点问题"这种模糊描述限制；
- 在保护隐私的前提下给出精准修复建议。

### 6.2 MCP 工具设计

采用「只读工具默认放行，修复工具必须确认」的分类。

#### 只读诊断工具（`readOnlyHint: true`, `idempotentHint: true`）

| 工具名 | 用途 |
|---|---|
| `netfix_get_global_state` | 当前网络路径、默认接口、IPv4/IPv6、网关、MTU、是否计费网络 |
| `netfix_get_interfaces` | 每个接口的类型、IP、状态、错误计数 |
| `netfix_get_dns_state` | 解析器列表、搜索域、DoH/DoT、接口级 DNS |
| `netfix_get_proxy_state` | 系统 HTTP/HTTPS/SOCKS/PAC/WPAD、是否认证、凭据是否存在（不含值） |
| `netfix_get_routes` | 路由表摘要、VPN/tunnel 接口 |
| `netfix_get_listeners` | 本机监听端口与进程 |
| `netfix_get_proxy_clients` | 检测到的 Clash/Surge/v2rayN 等客户端，只返回元数据 |
| `netfix_get_ip_reputation` | 当前出口 IP、ASN、ISP、住宅/数据中心、风险评分 |
| `netfix_dns_resolve(target, resolver)` | 用系统或指定解析器解析域名 |
| `netfix_ping(target, interface)` | ICMP 延迟丢包 |
| `netfix_trace_path(target, protocol)` | traceroute / mtr 结构化结果 |
| `netfix_test_proxy_for_url(url)` | 按系统代理访问 URL，返回实际使用的代理、状态、TLS 错误 |
| `netfix_test_direct_for_url(url)` | 直接访问 URL，与代理结果对比 |
| `netfix_check_proxy_auth()` | 检测代理是否需要认证、是否通过 |

#### 修复工具（`destructiveHint: true`，需确认）

| 工具名 | 用途 |
|---|---|
| `netfix_flush_dns()` | 刷新 DNS 缓存 |
| `netfix_renew_dhcp(interface)` | 强制 DHCP 续租 |
| `netfix_toggle_interface(interface, enabled)` | 开关网络接口 |
| `netfix_disable_ipv6(service)` | 临时禁用某服务的 IPv6 |
| `netfix_apply_proxy_profile(profile)` | 切换网络位置/代理配置 |
| `netfix_rollback_last_change()` | 撤销上一次修复 |

### 6.3 安全：防止凭据泄漏到 Prompt

- **服务端脱敏**：所有工具结果在返回给 Agent 前必须经过 DLP/脱敏层。
- 永远**不返回**：密码、UUID、Token、订阅 URL、Keychain 内容。
- 用结构化元数据替代敏感值：
  ```json
  {
    "proxy_http": {
      "enabled": true,
      "server": "127.0.0.1",
      "port": 7890,
      "requires_auth": true,
      "credential_present": true
    }
  }
  ```
- 工具描述中明确说明："本工具只返回网络配置元数据，凭据已脱敏。"
- 本地记录审计日志，便于用户自查 netfix 到底给 Agent 看了什么。

### 6.4 Agent 推理示例

#### 场景 A："ChatGPT 打不开"

1. Agent 调用 `netfix_get_global_state` → Wi-Fi satisfied，IPv4 正常。
2. `netfix_get_proxy_state` → 系统 HTTPS 代理 = `127.0.0.1:10808`。
3. `netfix_get_listeners` → 10808 无进程监听。
4. `netfix_get_proxy_clients` → 检测到 v2rayN，mixed inbound 端口是 10808，但进程未启动。
5. **结论**："v2rayN 配置监听 10808，但当前未运行，导致系统代理指向空端口。请启动 v2rayN。"

#### 场景 B："Codex CLI 报错网络问题"

1. `netfix_get_env_proxy` → 终端无 `HTTP_PROXY`/`HTTPS_PROXY`。
2. `netfix_get_proxy_state` → 系统代理 = `http://127.0.0.1:7890`。
3. `netfix_test_direct_for_url(api.openai.com)` → 失败 407。
4. `netfix_test_proxy_for_url(api.openai.com)` → 成功。
5. **结论**："Codex CLI 没继承系统代理，且当前网络需要代理认证。请在 shell 配置里 export https_proxy。"

#### 场景 C："换了节点还是 403"

1. `netfix_get_ip_reputation` → 出口 IP 为数据中心 ASN，AbuseIPDB 风险分 78。
2. `netfix_trace_path` → 路径正常，无丢包。
3. `netfix_test_proxy_for_url(chatgpt.com)` → 403。
4. **结论**："不是网络不通，而是出口 IP 被目标站风控。建议切换到住宅/移动 IP 节点。"

---

## 7. 竞品与监管环境（关键结论）

### 7.1 主要竞品

| 产品 | 类型 | netfix 差异 |
|---|---|---|
| **NetUtil** | 免费 macOS 网络工具 | 功能类似 ping/traceroute/dns，但不涉及代理/VPN 深度诊断 |
| **NetSpot / WiFi Explorer** | Wi-Fi 分析 | 专注 Wi-Fi 射频，不做代理链路诊断 |
| **iStat Menus** | 系统监控 | 看带宽/IP，不治网络病 |
| **Little Snitch** | 出站防火墙 | 控制连接，不解释为什么连不上 |
| **Proxifier** | 应用级代理 | 是代理客户端，netfix 是诊断层 |
| **ipcheck.ing / MyIP** | Web IP 工具箱 | 功能全面但非原生，无法读取本地配置 |
| **stormzhang/ipcheck** | Python CLI | 最接近，但无 GUI、无修复、无 Agent |
| **Surge** | 专业网络工具箱 | 功能极强但贵且复杂，netfix 定位更简单聚焦 |

**机会点**：市面上缺少一款**原生 macOS、小白友好、深度理解代理/VPN、能与 AI Agent 协作**的诊断自愈工具。

### 7.2 分发策略

- **主分发渠道：官网下载 + Developer ID 签名 + Notarization**。灵活、合规、利润空间大。
- **Mac App Store 谨慎**：沙盒禁止读取其他应用配置；如需读取代理客户端配置，很难上架。
- 可考虑「App Store Lite 版」只做系统网络诊断，完整版走官网下载。

### 7.3 法律与合规

- **中国大陆**：不销售/分发 VPN 服务，不内置节点，避免「翻墙」「科学上网」营销。可官网 Geo-block 大陆 IP。
- **隐私法规**：IP 属于个人数据；提供隐私政策；外部 API 调用需用户知情同意；支持缓存与关闭。
- **出口管制**：若使用 TLS/VPN/代理加密，需按 EAR 自分类（通常 5D992.c / ENC 豁免；开源项目做 TSU 通知）。
- **苹果合规**：使用公开 API；如需 Network Extension 需申请 entitlement；提交 PrivacyInfo.xcprivacy。

---

## 8. 升级后产品形态

### 8.1 应用主界面（Dashboard）

顶部：一键诊断大按钮 + 当前网络状态总览。

中部：分层状态卡片（红/黄/绿）：
- 🌐 本地网络（Wi-Fi / DHCP / 网关）
- 🔒 代理链路（系统代理 / 客户端 / 认证）
- 🌍 出口身份（IPv4/IPv6 / 住宅 or 数据中心 / 风险分）
- 🎯 目标服务（ChatGPT / Claude / YouTube / GitHub 等）

底部：最近诊断结论 + 建议动作。

### 8.2 诊断报告页

- **人话总结**：1 句话 + 3 句解释。
- **可视化链路**：本地 → 代理 → 中转 → 出口 → 目标，标红故障点。
- **一键修复**：安全修复按钮（Flush DNS、Renew DHCP、Disable IPv6、切换节点提示等）。
- **分享给 Agent**：生成脱敏 JSON，方便用户复制给 Kimi/Codex。

### 8.3 设置页

- 诊断范围：开启/关闭读取代理客户端配置、外部 IP 查询、信誉查询。
- 权限状态：显示 Full Disk Access、Location、Wi-Fi 等授权状态。
- Agent 集成：一键复制 `kimi mcp add` / `claude mcp add` 命令。
- 隐私中心：查看最近一次给 Agent 共享了哪些数据、清除本地缓存。

---

## 9. 升级路线图（Roadmap）

### Phase 0：战略确认与设计冻结（当前）

- [x] 完成产品战略 V2 文档。
- [ ] 与用户确认战略方向，锁定第一阶段实现范围。

### Phase 1：深度网络栈诊断（约 4-6 周）

目标：把诊断能力从「服务可达」推进到「全栈定位」。

- [ ] 实现分层诊断引擎：Wi-Fi、DHCP、DNS、网关、IPv4/IPv6、代理协议。
- [ ] 实现外部 IP / ASN / 住宅-数据中心 / 风险评分查询与缓存。
- [ ] 实现 DNS 泄漏、IPv6 泄漏检测。
- [ ] 实现代理协议探测（HTTP/SOCKS5/PAC/认证）。
- [ ] 实现 traceroute / mtr / networkQuality 包装与结构化输出。
- [ ] 更新 MCP server，暴露 `netfix_get_*` 与 `netfix_test_*` 工具。
- [ ] 为每个层级写好人话文案库（中/英）。

### Phase 2：人话解释与修复闭环（约 3-4 周）

目标：让小白用户能独立看懂并修复。

- [ ] 四段式结果卡片（Headline / Explanation / Actions / Detail）。
- [ ] 可视化链路图（本地 → 代理 → 出口 → 目标）。
- [ ] 一键修复按钮与撤销能力。
- [ ] AI 服务急救包：ChatGPT / Claude / Cursor / Copilot / GitHub / YouTube 等预设。
- [ ] 用户等级切换（小白 / 进阶 / 专家）。

### Phase 3：Agent 与权限模型（约 3-4 周）

目标：让 AI 安全、精准地拿到上下文。

- [ ] 实现安全的数据脱敏/DLP 层。
- [ ] 实现代理客户端元数据扫描（Clash / v2rayN / Surge / Stash）。
- [ ] 完善 MCP tool schema，支持 Kimi / Codex / Claude / Cursor。
- [ ] App 内「Ask AI」入口，让非 Agent 用户也能获得解释。
- [ ] 权限引导与隐私中心。

### Phase 4：商业化与分发（约 4-6 周）

目标：从工具到可持续产品。

- [ ] 官网落地页、下载页、中英文文案。
- [ ] 买断/订阅定价与支付（Stripe / 支付宝 / 微信）。
- [ ] 签名 + Notarization + `.dmg` 安装包。
- [ ] GitHub 开源 Lite 核心，Pro 功能闭源。
- [ ] 早期用户冷启动与案例收集。

### Phase 5：长期生态

- [ ] Windows 版（Python/Tauri）。
- [ ] 历史趋势与自动化监控（launchd 后台体检）。
- [ ] 团队版 / MDM / SSO / 审计日志。
- [ ] 与主流代理客户端官方合作（提供诊断 SDK）。

---

## 10. 关键指标（OKR）

### 短期（3 个月）

- 实现 10 层全栈诊断覆盖。
- MCP 工具在 Kimi 与 Codex 稳定调用成功率 > 90%。
- 10 位真实用户（含小白）完成首次诊断并给出反馈。

### 中期（6 个月）

- GitHub 开源 Lite 获得 1000+ stars。
- 付费用户 100+ 或付费转化率 > 5%。
- 收集 50+ 真实故障 case，沉淀为规则库。

### 长期（12 个月）

- 成为海外 AI 用户群体中知名的「Mac 网络自救工具」。
- 月收入覆盖持续开发成本。

---

## 11. 风险清单

| 风险 | 等级 | 应对 |
|---|---|---|
| 读取第三方代理配置引发隐私质疑 | 高 | 只做元数据+脱敏，默认不开启，用户可撤回权限 |
| 外部 IP/信誉 API 调用触发合规问题 | 中 | 默认本地诊断，外部查询需用户同意并缓存 |
| Mac App Store 无法上架完整版 | 中 | 主分发走官网签名+公证，Store 只放 Lite |
| 竞品快速跟进 | 中 | 靠 case 沉淀、中文体验、Agent 集成建立壁垒 |
| 中国大陆合规 | 高 | 不内置代理服务，官网可 Geo-block，避免敏感营销 |
| 技术复杂度膨胀 | 中 | 按阶段交付，先深后广，避免一次性做全平台 |

---

## 12. 结论与下一步

netfix 的下一个里程碑不是继续打磨现有 App 的皮肤，而是**把诊断深度做到全栈、把解释做到人话、把 Agent 集成做到安全可用**。

建议按以下顺序落地：

1. **Phase 1 深度网络栈诊断**：这是所有后续体验的基础。
2. **Phase 2 人话解释与修复闭环**：决定小白用户是否愿意用。
3. **Phase 3 Agent 与权限模型**：决定高级用户和 AI 工作流是否愿意用。
4. **Phase 4 商业化**：在前三个阶段验证后再推进。

**本战略的完成标准是：用户阅读并批准本文件，并明确指定下一步进入 Phase 1 或继续调整。**
