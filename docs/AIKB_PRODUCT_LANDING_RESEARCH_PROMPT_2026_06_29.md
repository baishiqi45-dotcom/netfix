# AIKB Product Landing Research Prompt - 2026-06-29

Copy this into AIKB / knowledge-base oriented dialogue.

```text
你现在作为 AIKB 参与 `/Users/qibaishi/Desktop/网络` 的 Netfix 产品落地闭环审计。你的角色不是写代码冲进主仓库乱改，而是做“宏观产品判断 + 证据优先研究 + 可执行落地设计”，为后续 Codex/工程线程执行铺路。

## 核心目标

从真实普通用户、顶级产品经理、顶级工程师、商业落地和合规边界五个视角，判断 Netfix 现在距离“本地可直接安装、普通用户能用、能形成诊断与代理配置闭环”的产品还差什么。

特别聚焦一个关键问题：

> Netfix 能不能做到用户把自己合法获得的住宅/自定义代理参数一键复制粘贴进 App，然后 App 自动解析、预检、验证、保存到 Keychain、监控、导出客户端配置包，并在用户确认后部署到 macOS 系统代理？

注意边界：
- Netfix 不销售住宅 IP。
- Netfix 不承诺“干净 IP”“防封”“绕过风控”“绕过平台限制”。
- Netfix 只处理用户自己合法获得的代理凭据。
- 任何系统代理改写必须显式确认、可回滚。
- 密钥、代理密码、API Key 不能回显、不能写日志、不能进截图证据。

## 优先读本地资料

先做内部检索，不要凭记忆判断。至少阅读或检索这些文件：

1. `/Users/qibaishi/Desktop/网络/README.md`
2. `/Users/qibaishi/Desktop/网络/docs/PRODUCT_AUDIT_AND_ROADMAP_2026_06.md`
3. `/Users/qibaishi/Desktop/网络/docs/PRODUCTIZATION_PLAN_2026_06_24.md`
4. `/Users/qibaishi/Desktop/网络/docs/RELEASE_CANDIDATE_SPRINT_2026_06_24.md`
5. `/Users/qibaishi/Desktop/网络/docs/NEXT_DIALOGUE_START_PROMPT_PRODUCT_COLD_AUDIT_2026_06_25.md`
6. `/Users/qibaishi/Desktop/网络/netfix/residential_proxy.py`
7. `/Users/qibaishi/Desktop/网络/netfix/proxy_bridge.py`
8. `/Users/qibaishi/Desktop/网络/netfix/api.py`
9. `/Users/qibaishi/Desktop/网络/gui/macos/Sources/Views/SettingsView.swift`
10. `/Users/qibaishi/Desktop/网络/gui/macos/Sources/Views/DashboardView.swift`
11. `/Users/qibaishi/Desktop/网络/gui/macos/Sources/Views/ProxySetupView.swift`
12. `/Users/qibaishi/Desktop/网络/tests/test_residential_proxy.py`
13. `/Users/qibaishi/Desktop/网络/tests/test_macos_proxy_export_ui.py`
14. `/Users/qibaishi/Desktop/网络/scripts/release_readiness.py`
15. `/Users/qibaishi/Desktop/网络/scripts/marketing_claims_check.py`

内部检索必须回答：
- 当前已支持哪些代理输入格式？
- 当前是否支持批量粘贴供应商列表？
- 当前是否能保存 profile、替换凭据、验证、监控、导出、应用到系统代理、回滚？
- 当前 macOS App 里用户路径是否像普通 App，还是仍像工程控制台？
- 当前测试覆盖是否证明“粘贴 -> 预检 -> 保存 -> 监控 -> 导出/应用 -> 回滚”闭环？
- 当前 DMG 是否已经是本地可安装包？离正式外发还差哪些门禁？

## 外部研究任务

做外部检索时只使用一手来源或可信项目主页：官方文档、GitHub 仓库、release、issue、security policy、license、README。不要把博客软文、搬运文章、广告站当事实。

需要研究的专题：

### 1. 代理输入格式与供应商列表格式

研究常见住宅/数据中心/移动代理供应商给用户的参数形态：
- `host:port:user:pass`
- `host,port,user,password`
- URL 形态：协议、用户名、密码、地址、端口
- SOCKS 形态：协议、用户名、密码、地址、端口
- 带国家、session、sticky、rotate、TTL、ASN、city、protocol 的表格或 CSV
- API 拉取 proxy list 的场景

输出：
- Netfix 当前 parser 覆盖矩阵。
- 缺失格式列表。
- 建议的 parse normalization schema。
- 错误提示应该如何讲人话。
- 哪些字段必须进入 Keychain，哪些字段可以明文存在本地 profile。

### 2. 本地部署路径

研究 macOS 上合法配置代理的路径：
- 系统 HTTP/HTTPS/SOCKS 代理。
- PAC 文件。
- 本地 127.0.0.1 bridge，把认证上游代理变成系统可用代理。
- 子进程环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`。
- 导出给客户端而不是改系统，例如 Mihomo/Clash、sing-box、Surge、Stash、Shadowrocket 等。

输出：
- 哪条路径最适合普通 macOS App 默认使用。
- 哪条路径风险大，必须折叠到高级。
- 当前 Netfix 的 bridge 方案是否足够，缺什么。
- 如何设计“部署前预览”和“部署后验证/回滚”。

### 3. 可参考开源项目与可借鉴组件

内外检索可能有用的开源项目。不要直接安装，不要执行第三方脚本。只做候选研究和适配建议。

候选类别：
- 代理核心与配置生态：sing-box、mihomo/Clash Meta、xray-core、v2ray-core。
- 桌面代理客户端：Clash Verge Rev、v2rayN、v2rayU、Nekoray/NekoBox、sing-box GUI 相关项目。
- 配置格式与订阅转换：subconverter、相关 YAML/JSON schema 或 parser。
- macOS 系统代理/网络设置相关工具或库。
- 本地菜单栏 App、Sparkle auto-update、Developer ID/notarization、Keychain 存储、privileged helper/SMAppService/SMJobBless 相关参考。
- 本地 HTTP API / MCP 工具安全模型参考。

对每个候选输出：
- 项目名、URL、license、活跃度信号、核心能力。
- 能给 Netfix 带来什么。
- 是否可直接依赖、只借鉴设计、还是拒绝。
- 安全/许可/体积/维护风险。
- 与“本地可安装桌面 App，不做网站”的关系。

### 4. 产品闭环与信息架构

从普通用户任务视角重画 Netfix：

P0 闭环：
1. 打开本地 App。
2. 一键诊断。
3. 人话结论：当前是 DNS、系统代理、代理客户端、节点、证书、Wi-Fi、目标服务还是 API Key 问题。
4. 如果用户有住宅/自定义代理：粘贴参数。
5. App 自动解析并脱敏预览。
6. 验证可用性、出口身份、DNS/IPv6 风险、目标服务矩阵。
7. 保存 profile 到本地，密码写 Keychain。
8. 启动监控。
9. 根据用户选择：
   - 仅导出客户端配置包；
   - 仅给某个子进程使用；
   - 确认后应用到 macOS 系统代理；
   - 一键回滚。
10. 失败时给下一步：换候选、更新凭据、导出客户端包、恢复系统代理、问 AI。

输出：
- 当前 Netfix 哪些步骤已经闭环。
- 哪些步骤只是后端有能力但 UI 不像产品。
- 哪些步骤完全缺失。
- P0/P1/P2 Roadmap，不超过 2 周可执行切片。

## 必须避免的误区

- 不要建议把 Netfix 变成网站。目标是本地可安装 macOS App，Web 控制台最多是高级/开发辅助界面。
- 不要把 AIKB 当运行时仓库，不要把产品代码搬进 AIKB。
- 不要因为外部项目存在就建议依赖；先判断体积、安全、许可、维护成本。
- 不要建议自动静默改系统代理。
- 不要建议抓取、购买、销售、绕过平台风控的住宅 IP。
- 不要输出“可绕过检测”“防封”“干净 IP”之类营销语。
- 不要泄露、复述、归档任何真实代理密码、API Key、token。
- 不要只写宏大报告。必须给后续工程线程能直接执行的任务包。

## 输出格式

请用下面结构输出。

### 0. Route Status

用 AIKB ledger 说明：
- repo_role_decision: knowledge_routing_capability_repo
- mode: research_and_design_only
- runtime_writeback: no
- external_install: no
- secrets_handling: no secrets copied or stored

### 1. Executive Verdict

用 10 句话以内回答：
- Netfix 当前是不是已经像产品？
- 离本地可安装可用还差什么？
- “一键复制粘贴参数部署住宅/自定义代理”现在能做到几成？
- 最关键的 3 个 P0 缺口是什么？

### 2. Product Closure Map

做表格：

| User Step | Current Support | Evidence | Gap | Recommended Product Behavior | P0/P1/P2 |

必须覆盖：
- 首次安装/打开
- 一键诊断
- 问 AI
- 粘贴代理参数
- 批量导入候选
- 预检/验证
- 保存 Keychain
- 监控
- 导出客户端配置包
- 应用到系统代理
- 桥接失效恢复
- 回滚
- 日志/报告
- 发布/更新

### 3. Residential Proxy One-Paste Deployment Spec

给一个清晰产品规格：
- 输入框接受什么。
- 解析后展示什么。
- 哪些字段脱敏。
- 验证矩阵是什么。
- “保存并监控”按钮做什么。
- “应用到系统代理”按钮如何确认、如何备份、如何回滚。
- “导出客户端配置包”包含哪些文件。
- 失败状态怎么提示。
- 什么永远不自动做。

### 4. Research Backlog

按专题列出需要补强的资料和候选项目：

| Topic | Why It Matters | Sources To Check | Expected Decision | Risk |

每条必须能帮助提高产品力，而不是泛泛收藏链接。

### 5. Open Source Candidate Ledger

对检索到的开源项目做 ledger：

| Candidate | URL | License | Useful Capability | Use Mode | Risk | Decision |

Use Mode 只能是：
- reference_only
- optional_export_target
- test_fixture_reference
- possible_dependency_after_audit
- reject

### 6. Engineering Task Pack

把后续落地拆成工程可执行任务，每个任务写：
- objective
- files likely touched
- acceptance tests
- product acceptance
- risk/rollback

至少包含：
1. 普通用户代理粘贴向导重设计。
2. Parser 覆盖供应商表格/CSV/URL/host-port-user-pass。
3. 代理候选验证矩阵和结果人话化。
4. 保存并监控 profile 的桌面 UI。
5. 客户端配置包导出质量提升。
6. 系统代理应用前预览/确认/回滚。
7. 桥接进程生命周期可视化。
8. DMG 安装/首次打开/权限/更新闭环。
9. AI 解释如何围绕“下一步动作”而不是技术状态。

### 7. Harness And Evidence Plan

回答是否需要 harness。必须包含：
- Parser fixture corpus：真实格式但假凭据。
- Fake upstream HTTP/SOCKS proxy for integration tests。
- Local identity probe mock，避免测试依赖真实住宅 IP。
- UI snapshot tests / Playwright 或 macOS UI smoke。
- DMG smoke：双击 App、启动 backend、保存 profile、导出包、验证 rollback。
- Security tests：密码不进日志、不进报告、不进截图。

### 8. What Not To Build

明确列出现在不要做的东西：
- 不要做网站化 SaaS。
- 不要卖 IP。
- 不要承诺防封/干净 IP。
- 不要自动静默改系统代理。
- 不要接入未经审计的第三方二进制作为默认依赖。
- 不要把 AI 当执行引擎。

### 9. Final Recommendation

用非常直接的话给结论：
- 当前下一步最应该让工程线程做什么。
- 哪些研究必须先完成。
- 哪些功能已经足够不要再堆。
- 什么时候可以说“本地可安装产品闭环基本成立”。

## 验收标准

这次 AIKB 输出合格的标准：
- 每个判断都有本地文件证据或外部来源链接。
- 明确区分“已实现”“后端有但 UI 不产品化”“缺失”“不该做”。
- 能直接指导下一轮 Codex 落地执行。
- 尊重本地桌面 App 方向，不把产品带偏成网站。
- 不产生任何秘密、凭据、真实代理 URL。
```
