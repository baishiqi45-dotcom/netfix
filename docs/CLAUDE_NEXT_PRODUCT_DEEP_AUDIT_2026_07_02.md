# Netfix 下一阶段产品深度审计（2026-07-02）

> 范围：`<repo>` working tree，commit fc3ed77
> 立场：顶级产品经理 + 顶级工程负责人 + 最普通小白用户 + 开源增长负责人
> 语气：尖锐，证据优先，每条判断尽量绑定文件/函数/界面/命令
> 上一轮：见 `docs/CLAUDE_MACRO_PRODUCT_STAR_AUDIT_2026_07_01.md` / `docs/KIMI_ORDINARY_USER_STAR_GROWTH_AUDIT_2026_07_01.md` / `docs/PRODUCT_MACRO_AUDIT_2026_06_30.md`

---

## 0. 一句话判决

**Netfix 已经把"local-first 网络诊断 + 代理粘贴部署 + Agent 能力层"三件事的代码全部写完了，但 GitHub 首屏把它包装成"工程师脚本"，SwiftUI 把用户推入"两次确认 + 缩写按钮"的迷宫，MCP 工具能跑却不会让 Agent 真的自主决策。三件事里任意一件都是劝退。它现在是 80 分的项目、30 分的产品、20 分的开源增长。**

---

## 一、宏观定位审计：Netfix 到底是什么

五个候选定位横向比较：

| 候选定位 | 用户心智 | Netfix 实际匹配度 | 拿 Star 难度 |
|---|---|---|---|
| 网络修复工具 | "Mac 上不了网，我装它" | 中：缺 dev-friendly 文案 + 一键回滚+ 主代理核心是 black-box | 高 |
| 代理部署工具 | "我有代理不会用，我装它" | 高：粘贴 → 预检 → 部署 → 回滚闭环确实成立 | 低-中 |
| AI Agent 的本地网络观测层 | "Codex/Claude 调它看网络" | 中：30 个 MCP 工具齐全但 schema 缺 output/evidence | 高（需要先教育市场） |
| 开源开发者工具 | "搞 macOS 的收藏一个" | 中：技术深度有，文案/截图/对比严重不足 | 中 |
| 普通用户 Mac 网络急救 App | "我装个 App 自己用" | 低：首屏写"AI 开发工具断线急救"、确认短语英文、状态卡显示内部 ID | 极高（要重写） |

**最强定位（一句话讲清楚）**：

> **"买了代理不会配？粘贴一行，Netfix 帮你让 Mac 安全上网；改坏了一键还原。Codex/Claude/Kimi 也能调它看网络。"**

定位核心矛盾：当前 README 同时讲"代理粘贴部署"和"AI 服务断线急救"。普通用户 5 秒无法判断它属于哪类。

- 65% 命中：**已经买了代理但不会配 Mac 的人**（普通用户）
- 25% 命中：**Agent 用户**（开发者人群，但落地形态是 MCP）
- 10% 命中：**网络断了想自救的小白**

**结论**：Netfix 当前应该把 65% 的"代理粘贴部署"作为唯一主定位，AI/Agent 折叠到第二屏。

证据：
- `README.md:13-19` 写了 3 件事，但首屏标题"它做什么"没有一句话讲"我帮你让 Mac 配代理"
- `README.en.md:14` 同样
- `gui/macos/Sources/Views/DashboardView.swift:412` "粘贴你已有的代理参数" 已经是按钮文案了，但被埋在 proxyDeploySection（Dashboard 二级 section）
- `gui/macos/Sources/Views/ProxySetupView.swift:31` 标题"添加你的代理"——产品已经偷偷把自己定位成"代理粘贴"，但首屏文案还是把它当"网络急救"

**修复方向**：把 `DashboardView.swift` 第一屏从"状态卡 + 一键诊断"重构成"粘贴代理 → 预检 → 部署"三按钮 wizard（见 §2、§4）。

---

## 二、普通用户冷审：最刺耳的 20 个问题

按用户路径"打开 GitHub → 安装 → 打开 App → 粘贴 → 部署 → 出错 → 回滚 → 退出"顺序，每条给出文件位置和具体修复。

### Q1：我点进 GitHub 首页 5 秒内搞不清它是干啥的
- **现状**：`README.md:5-10` 显示 4 个 badge + 一张 hero 图，hero 图我看不到内容（路径 `assets/github/hero.zh.png`，KIMI 报告说只是概念图）。我没看到一行普通人的话告诉我"我是你买代理不会配时的助手"。
- **位置**：`README.md:13` "它做什么"段的第一行是"已有合法代理参数但不会配置 Mac"——这句话在普通用户眼里是英文合同。
- **修复**：首屏首句改为 "**你的 Mac 不会用你买的代理？把服务商给你的一行连接信息粘贴进来，Netfix 帮你让这台 Mac 安全上网；改坏了一键还原。**"

### Q2：两个 `curl | bash`，我该复制哪个
- **现状**：`README.md:24-29` 两个 curl 一个装 App，一个装 MCP。普通用户分不清。
- **修复**：标黄"普通用户复制这一行"，另一个折叠"开发者 / Codex 用户点这里"。

### Q3：QA DMG 还没签名我不知道，复制完 curl 我只能看到「无法验证开发者」
- **现状**：`README.md:55` 在第三段才承认"未签名"。`README.md:24` 第一行 curl 之前没有任何警告。
- **修复**：在 `curl | bash` 上方加 ⛔ 黄色 warning block：「这是 v0.2.0-qa.1 预览版。DMG 未签名未公证。首次启动要进"系统设置 → 隐私与安全性 → 仍要打开"。`README.md:25-26` 改顺序：先 warning 后命令。」

### Q4：装完打开 App 第一屏写"AI 开发工具断线急救"
- **现状**：`WelcomeView.swift:17`（旧文档提及，现在 `ProxySetupView.swift:30-31` 已改为"添加你的代理"——但是 5/26 之前的状态是 onboarding 标题工程师腔）
- **修复**：实测打开，第一屏做两选一："我有代理账号 → 粘贴" / "我没代理 → 检查网络"。不要把 onboarding 当广告位。

### Q5：粘贴框我不知道该粘贴什么
- **现状**：`ProxySetupView.swift:69` 写"复制下来大概是：地址:端口:用户名:密码 这种样子。不要只复制出口 IP。"——普通用户看到还是懵。
- **修复**：粘贴框 placeholder 直接给一行示例："例如 proxy.example.com:8001:用户名:密码"。下面再给 4 种支持的格式 + 3 种不支持的（ss/vmess/订阅链接）。

### Q6：粘贴错误时反馈是英文 "unsupported protocol: vmess"
- **现状**：`residential_proxy.py:1055-1062` 错误仍是英文技术词。"unsupported protocol: vmess" / "port must be between 1 and 65535" / "username is required when password is provided" 全是英文。
- **修复**：在 `residential_proxy.py:1018-1069` 错误信息直接换成中文，并把"建议下一步动作"附加在错误对象里（参考 `deployment_decision.next_steps`）。前端 `ProxySetupView.swift:191` 的"失败：\(error.localizedDescription)"直接显示底层 error，要把中文映射做完。

### Q7：保存按钮写"保存并测试（暂不改网络）"——我保存了为什么还不能上网？
- **现状**：`ProxySetupView.swift:91-92` 按钮文案已经做了改进（Kimi 报告后），但仍然分两步。
- **修复**：合并为单页 wizard（`ProxySetupView.swift` 重构见 §10），底部只一个主按钮"开始使用这台 Mac 上网"。

### Q8：点"开始使用"还要弹"Netfix 会先备份当前网络设置…"——好吓人
- **现状**：`ProxySetupView.swift:171-180` 弹出 `confirmationDialog("开始使用这台 Mac 上网？")` —— 文案已经写"会先备份"，但还提到"这组代理需要 Netfix 保持打开"——为什么我的 Mac 要一直开着它？没说清楚。
- **修复**：弹窗文案改成：「要让你这台 Mac 用刚才保存的代理上网吗？Netfix 会先把你原来的网络设置备份到本地，反悔时一键还原。如果代理带账号密码，Netfix 需要保持打开来代管密码。」

### Q9：状态卡显示 "• proxy_core_status" — 这是啥？
- **现状**：`DashboardView.swift:204` `Text("• \(item.displayTitle)")` 优先用 displayTitle，但底层仍然暴露 name 给 `DisclosureGroup("查看技术详情")`——这没问题。问题在 `DashboardView.swift:170-174` `statusGroups` 把 proxy_core、egress、service 这些原始 layer id 作为分组依据，UI 不翻译。
- **修复**：在 `DashboardView.swift:170-174` 把 group id 改成人话（已经在 title 里做了，但 ids 还在用 engineering 字符串，PR 风险低，重命名即可）。

### Q10：失败时错误 banner 只有 "重试 / 复制错误 / 查看日志" 三个按钮
- **现状**：`DashboardView.swift:314-336` `errorBanner(_ message:)` 只有 retry/copy/showLogs。`DashboardView.swift:380-392` `friendlyErrorMessage` 把常见错误翻译成中文，但**没有给出修复按钮**。
- **修复**：复用 `explanationCard` 的 `primaryAction` 模式，error banner 里再加一个"一键修复"按钮，调用 `viewModel.executeAction(recommendedAction)`。

### Q11：代理连不上时显示"代理端口拒绝连接，请检查端口或换一个候选"——我哪来的候选？
- **现状**：`SettingsView.swift:1296-1311` `friendlyProxyError` 翻译得不错，但说"换一个候选"——前端根本没显示候选列表。
- **修复**：`proxyImportPreviewResult` 的 `candidates` 已经在 `proxyImportPreviewBlock` 渲染了，但只出现一次（`SettingsView.swift:1419-1475`），失败时不会主动 re-preview。加一行："上次预检里还有 X 条候选可用，[点这里重看]"。

### Q12：回滚在哪？首页底部那个"恢复原来的网络设置"我看 5 遍没意识到
- **现状**：`DashboardView.swift:764-769` "恢复原来的网络设置" 是 `borderless` 按钮，埋在 `secondaryActionToolbar`（`DashboardView.swift:772-804`），旁边还有"代理/日志/设置"三个。
- **修复**：如果 `proxyBridgeState.lifecycle.status == "running_system"`（即当前正在用 Netfix 代理），把"恢复原来的网络设置"提升到顶部 toolbar，用橙色实色按钮。

### Q13：退出 App 时弹"恢复网络设置后退出/取消退出/仍然退出" 三按钮——我不敢按
- **现状**：`AppDelegate.swift:149-169` 三按钮存在但 `tests/test_macos_quit_bridge_guard.py:11-31` 全是字符串字面量测试，无 e2e。
- **修复**：按钮文案改成"先还原再退出"（destructive）/ "我再想想"（cancel）/ "退出（可能上不了网）"。明确告诉用户不还原会怎样。

### Q14：我担心 App 偷我的代理密码
- **现状**：`README.md:226-230` "安全边界"段写了，但首屏没看到。`SettingsView.swift:134` "删除日志、设置、AI 预算账本和已保存密钥" confirmation 提了一句"AI 密钥和代理密码"——但要在 Keychain 那块加可视化的"现在 Keychain 里有什么"。
- **修复**：README 首屏加 `## 安全与隐私速览` 6 行 bullet（参 KIMI 报告 §8）。Settings → 权限 Tab 加一个"Keychain 中存了什么"按钮，列出 service/account，但不显示值。

### Q15：AI 弹窗里"我确认发送脱敏诊断报告" —— 脱敏诊断报告是啥？
- **现状**：`DashboardView.swift:941-945` Toggle 文案"我确认发送脱敏诊断报告\(images.isEmpty ? "" : "和上方图片")给已配置的云端模型"。"脱敏诊断报告"对小白是黑话。
- **修复**：改成"允许 AI 看你这次的网络检查结果（密码和明文 IP 已经自动隐藏）。如果不勾，AI 完全不会收到任何东西"。

### Q16：AI 弹窗"AI 可不填"是什么意思？
- **现状**：`DashboardView.swift:415` "不需要 API Key 也能用"——已经修了，但放在右上角徽章位，小白不一定注意。
- **修复**：把这个徽章改名为"无 AI 也照常用"，放到 AI 弹窗标题下面一行解释。

### Q17：设置 6 个 Tab，我找不到换 API Key 在哪
- **现状**：`SettingsView.swift:75-111` 6 Tab：general/proxy/agent/ai/permissions/about。
- **修复**：合并为 3 Tab：常规 / AI / 高级。proxy 折叠到常规的"代理"section，agent 折叠到高级，permissions 折叠到高级。

### Q18：MCP 注册到底改了我电脑的什么？后悔了怎么卸？
- **现状**：`SettingsView.swift:279-355` agentTab 给了"复制给 Codex/复制 Kimi/复制全部"按钮，但没显示改了什么文件、没"一键卸载"按钮。
- **修复**：Agent Tab 底部加"注册后改了哪些文件"+ "卸载"按钮。

### Q19：我不接 API Key 是不是残血版？
- **现状**：`README.md:126` "不接 API Key 能用吗？/ 能"——已答，但 AI Tab 缺一个"我不接 AI"开关/说明。
- **修复**：AI Tab 顶部加 banner："不需要 API Key。Netfix 默认用本地规则解释结果。要让云端 AI 再说一遍人话时才需要 Key。"

### Q20：我粘贴了 Clash 订阅链接，弹"unsupported protocol: vmess"，怎么办？
- **现状**：`README.md:135` "暂不支持 `ss://`、`vmess://` 或 Clash/sing-box 订阅链接"。但用户要先粘贴才知道不支持。
- **修复**：粘贴框 placeholder 加 "❌ 不支持 ss://、vmess://、订阅链接"。检测到这些 scheme 时，主动给"Netfix 只支持 HTTP/SOCKS5 四段参数。请联系服务商索取"。

---

## 三、开源 Star 增长审计：为了更多 Star 最该做的 15 件事

按 ROI 排序。

| # | 动作 | 收益 | 成本 | 状态 |
|---|---|---|---|---|
| 1 | README 首屏重写：标题 + 5 秒能看懂的承诺 + 一行主 CTA + 安全速览 | 极高 | 低 | 部分（CLAUDE 报告后已加 4 段，KIMI 报告后未做） |
| 2 | 6 张真实 App 截图 + 2 个 GIF（粘贴→预检→部署 / 失败一键修复） | 极高 | 中 | **未做** |
| 3 | 顶部加 ⛔ 未签名 warning block | 高 | 低 | **未做** |
| 4 | FAQ 小节（"会不会改坏网络""不接 Key 能不能用""脱敏是什么""GitHub Issue 我贴密码怎么办"） | 高 | 低 | **部分** |
| 5 | 把 3 个 cases 提到首屏"真实用户故事"，每条 1 行 + 链接 | 高 | 低 | **未做**（README:96-104 写了，但埋得深） |
| 6 | 跟 ClashX/Surge/mihomo/sing-box/Proxyman/mitmproxy/Tailscale 的对比表（README 已 4 行，再扩到 6 行） | 高 | 低 | 部分 |
| 7 | Topics 增加 `homebrew-cask`、`raycast`、`agent`、`macos-app`、`diagnostics` 删 `clash/mihomo/sing-box` | 中 | 低 | 部分（CLAUDE 后是 30 个但还保留 clash/mihomo/sing-box） |
| 8 | PR template 加 "Output Schema Impact" 强制约束 | 中 | 低 | 已做 |
| 9 | 中文 HackerNews/V2EX/NodeSeek 三篇"一个用户痛点"导流贴 | 高 | 中 | **未做** |
| 10 | Show HN：标题 "Show HN: I built a macOS network self-rescue app that pastes your proxy and tells you which layer broke" | 极高 | 中 | **未做** |
| 11 | 加 `BREAKING.md` / `CHANGELOG.md` / `ROADMAP.md` 三个文件 | 中 | 低 | **未做** |
| 12 | 加 GitHub Social Preview 图片（1280×640）| 中 | 低 | **未做** |
| 13 | 加 `cases/INDEX.md` 把所有脱敏 case 索引化 | 中 | 低 | **未做** |
| 14 | Repo description 改"paste proxy + tell me which layer broke"（当前是 engineer 腔） | 高 | 极低 | **未做**（`repository.yml:3` 还是工程师腔） |
| 15 | 增加英文 README 在 Reddit r/macapps/r/MacOS 投放 | 中 | 中 | **未做** |

**记忆点候选**（一句话能让人记住的）：
- "粘贴一行，Mac 上网；改坏一键还原。"（普通用户视角）
- "Codex 说你网络挂了？让 netfix 替你查。"（Agent 视角）
- "本地优先 + Keychain + 脱敏 + 回滚 = 网络自修。"（安全视角）

---

## 四、功能成熟度审计（0-10）

| 闭环项 | 评分 | 证据 / 差在哪 |
|---|---|---|
| 一行安装 Mac App | 7 | `scripts/install_mac_app_from_github.sh` 完整（193 行），但 DMG SHA256 默认硬编码且 `NETFIX_DMG_SHA256` 完全旁路；未签名 DMG 第一次打开 Gatekeeper |
| 一行安装 Codex MCP | 8 | `scripts/install_codex_mcp_from_github.sh` 完整（189 行），zip-slip 防护好；缺 Kimi/Claude/Cursor 自动注册 |
| Claude/Kimi/Cursor MCP 配置路径 | 3 | `SettingsView.swift:281-340` 只有"复制 Kimi/通用配置"按钮，但 Kimi 真的 `mcp add` 不一定支持；Claude Desktop 路径未引导；Cursor 路径未引导 |
| 不接 API Key 离线可用 | 9 | `SettingsView.swift:373` "没有 API Key 也能诊断…"已写；`llm_explain.explain_with_llm` fallback 到本地规则（已确认） |
| 接 API Key 后的 AI 问答 | 8 | `mcp_server.py:101-140` `netfix_explain_llm` 完整；`redaction` 前置；`safe_action_map` 本地 allowlist（`llm_explain.py:98-120`） |
| 粘贴代理参数 | 7 | `ProxySetupView.swift:78-84` 有 UI，但粘贴框不实时解析；错误信息英文 |
| 参数格式识别 | 7 | `residential_proxy.py:1006-1100` `parse_proxy_input` 支持 URL/host:port:user:pass/host,port,user,pass；不支持 ss/vmess/订阅链接且没在错误时主动告知 |
| 代理预检 | 8 | `residential_proxy.py:1644-1731` `validate_proxy_profile` 完整；TCP+HTTP+IDENTITY 三段 |
| Keychain 保存 | 7 | `keychain.py:29-53` 写入走 stdin（防 argv 泄露）；`is_available()` 不过滤 macOS 版本；`add-generic-password -U` 无 ACL，同 user 进程可读 |
| 系统代理部署 | 7 | `residential_proxy.py:1847-2056` `apply_proxy_profile` 完整：备份 → 应用 → 验证 → 回滚；`SYSTEM_APPLY_CONFIRMATION = "APPLY_PROXY_PROFILE"` 已升级；UI 文案已中文化 |
| 回滚 | 8 | `residential_proxy.py:2059-` `rollback_last_proxy_apply` + `proxy_apply_journal.json` 完整；UI 三按钮存在 |
| IPv6 问题处理 | 4 | `residential_proxy.py:1424-1474` `_ipv6_leak_assessment` 永远返回 `"status": "unknown"`（KIMI 报告 P1-7 已指）；`apply_proxy_profile` 没真正调 `-setv6off`；journal 里 `ipv6.disabled_during_apply` 写了但实际命令在 `_disable_ipv6_commands`（`residential_proxy.py:817-821`）只在 restorable 时调 |
| 日志脱敏 | 4 | `report.py:192-216` `_persistent_data` 调用 `redact_report`，OK；但 `logs.append_event` 完全不脱敏（旧审计 P0-2 未修）；`agent_tools` 的 stderr 走 `_safe_text` 脱敏但不全面 |
| 错误解释 | 6 | `explain.py` + i18n 翻译了一部分（`i18n/zh_CN.json` 39 行，覆盖 status/summary/section/label/fix/manual_step/service.group）；UI 的 `friendlyErrorMessage`（`DashboardView.swift:380-392`）和 `friendlyProxyError`（`SettingsView.swift:1296-1311`）做了；缺 `friendlyAIError` |
| GitHub Issue 脱敏报告 | 5 | `release_preflight.py` + `release_audit.py` 工作区扫描 OK；`release_evidence.py` 存在但不知是否真生成脱敏报告 bundle；`docs/github/STAR_GUIDE.md:78-84` 列了"绝对不能贴"，但缺一键生成 `safe_diagnostic_report` 工具 |
| CI/release gate | 6 | `.github/workflows/ci.yml` 跑了 syntax/CLI smoke/API smoke/MCP smoke/pytest/release-audit/marketing-claims/source-export；**没跑** release_preflight --with-dmg-smoke、没跑 release_gate.sh --strict-workspace |
| unsigned DMG 信任问题 | 2 | `install_mac_app_from_github.sh:198` 最后一句"macOS says the developer cannot be verified, this DMG is not ready for public non-technical distribution"——**完全没硬约束**；任何人都可以无视这一行直接喊"装一下就能用" |

---

## 五、Agent / MCP 创新方向（schema 级）

当前 30 个 MCP 工具（`mcp_server.py:42-278`）是"广度优先"：每个都返回 dict，缺 schema、缺 output、缺 evidence。Agent 拿到数据不知道怎么用。

**下一代 MCP 应该有的 10 个新工具**（按优先级）：

### 5.1 `netfix_list_fixes`
- **作用**：让 Agent 发现"现在能做哪些修复"
- **input schema**：
```json
{
  "type": "object",
  "properties": {
    "tier_filter": {"type": "integer", "enum": [1, 2, 3]},
    "category": {"type": "string", "enum": ["network", "dns", "proxy", "ipv6", "tls", "service"]}
  }
}
```
- **output schema**：
```json
{
  "type": "object",
  "properties": {
    "fixes": {"type": "array", "items": {"$ref": "#/definitions/FixDescriptor"}}
  },
  "definitions": {
    "FixDescriptor": {
      "type": "object",
      "properties": {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "tier": {"type": "integer"},
        "category": {"type": "string"},
        "risk": {"type": "string", "enum": ["safe", "mutate_network", "mutate_credentials"]},
        "requires_confirmation": {"type": "boolean"},
        "requires_magic_word": {"type": "boolean"},
        "estimated_seconds": {"type": "integer"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### 5.2 `netfix_dry_run_fix`
- **作用**：预演修复，返回将要执行的命令（脱敏）+ 影响面
- **input**：`{ "issue_id": "flush-dns-cache" }`
- **output**：
```json
{
  "preview": {
    "commands": [{"binary": "dscacheutil", "args": ["-flushcache"], "risk": "readonly"}],
    "mutates": {"network": false, "credentials": false, "system_proxy": false},
    "rollback_supported": true,
    "rollback_strategy": "noop",
    "evidence_chain": [{"diagnostic": "dns_resolver_stale", "weight": 0.8}]
  }
}
```

### 5.3 `netfix_apply_fix`
- **作用**：执行修复；Tier 2 必须 `magic_word: "APPLY_SYSTEM_FIX"` 二次确认
- **input**：
```json
{
  "type": "object",
  "required": ["issue_id"],
  "properties": {
    "issue_id": {"type": "string"},
    "dry_run": {"type": "boolean", "default": false},
    "confirmed": {"type": "boolean", "default": false},
    "magic_word": {"type": "string", "description": "Required for tier>=2; must equal APPLY_SYSTEM_FIX"}
  }
}
```

### 5.4 `netfix_evidence_chain`
- **作用**：返回"为什么是这条根因"的证据链（KIMI 报告 P1-1 已指缺）
- **output**：
```json
{
  "root_causes": [{
    "id": "rc_dns_via_proxy_core",
    "description": "DNS queries going through proxy core but upstream resolver returns 0.0.0.0",
    "confidence": 0.85,
    "evidence": [
      {"diagnostic_id": "dns_openai", "status": "fail", "weight": 0.6},
      {"diagnostic_id": "system_proxy_state", "status": "ok", "weight": 0.2}
    ]
  }]
}
```

### 5.5 `netfix_sanitized_report`
- **作用**：返回脱敏后的最新报告（用于云端 AI 上传）
- **input**：`{ "level": "balanced" | "strict", "include_diagnostics": true }`
- **output**：`{ "redacted_report": {...}, "redaction_audit": {...}, "redacted_report_hash": "..." }`

### 5.6 `netfix_proxy_credential_doctor`
- **作用**：解析 + 诊断 + 给建议（不存密码）
- **input**：`{ "raw_credential": "..." | null, "host": "...", "port": 8001, "username": "...", "password": "..." }`
- **output**：
```json
{
  "diagnoses": [
    {"code": "unsupported_scheme", "severity": "error", "message": "vmess:// 暂不支持"},
    {"code": "ambiguous_protocol", "severity": "warn", "message": "未指定协议；默认按 HTTP 处理"}
  ],
  "redacted_url": "http://user:***@proxy.example.com:8001",
  "precheck_recommendation": "this line can be deployed after redaction"
}
```

### 5.7 `netfix_explain_for_user`
- **作用**：把诊断结果翻译成"隔壁同事都能听懂"的话
- **input**：`{ "audience": "user" | "engineer" }`
- **output**：`{ "headline": "网络没问题，代理账号不对", "what_to_do_next": ["去代理后台重新复制一遍账号", "点重新检查"] }`

### 5.8 `netfix_explain_for_engineer`
- **作用**：返回证据链 + 命令预览 + 影响面
- **input**：`{ "issue_id": "..." }`
- **output**：同 `dry_run_fix.preview` + evidence_chain + raw_diagnostic_slice

### 5.9 `netfix_ask_followup_question`
- **作用**：当缺信息时，**只问一个**最关键问题
- **input**：`{ "context": "proxy_deploy" | "diagnose" | "fix", "ambiguity_code": "..." }`
- **output**：`{ "question": "你的代理服务商给你的是 host:port:user:pass 还是 URL？", "options": ["host:port:user:pass", "http://user:pass@host:port", "I don't know"] }`

### 5.10 `netfix_export_issue_bundle`
- **作用**：一键生成脱敏 issue 包（zip）
- **input**：`{ "include_logs": true, "include_last_report": true }`
- **output**：`{ "bundle_path": "/tmp/netfix-issue-2026-07-02.zip", "redacted_report_hash": "...", "size_bytes": 12345 }`

---

## 六、安全与隐私深挖（P0 / P1 / P2）

### P0（必须修）
- **P0-1**：MCP `_strip_internal_secrets` 只覆盖 `_secret` 字段，但 `redaction._redact_string` 不脱敏 `socks5://` URL 中的密码（`redaction.py:36` `URL_RE` 不包含 socks5 协议覆盖错漏）。**位置**：`netfix/redaction.py:36` + `netfix/mcp_server.py:337-345`。**修复**：`URL_RE` 改成 `\b(?:https?|socks5h?|socks5)://...`
- **P0-2**：`logs.append_event` 完全不脱敏（KIMI 报告 P0-2 已指）。**位置**：`netfix/logs.py:89-99`。**修复**：写盘前 `redaction.redact_report(event, level="balanced")`。
- **P0-3**：`agent_tools.get_global_state` 硬编码 `"platform": "darwin"`（旧 CLAUDE 报告 P0-1）。**位置**：`netfix/agent_tools.py:120`。**修复**：`platform.system().lower()`。
- **P0-4**：`safety.classify_command` 用子串匹配（`safety.py:71` `if any(kw in lower for kw in _SUDO_KEYWORDS)`）—— `"su do something"` 会假阳性；`"curl ... | bash"` 已经用正则，但 `"curl ... | sh"` 也已加。**位置**：`netfix/safety.py:69-78`。**修复**：改用 `\b(sudo|networksetup|pfctl|socketfilterfw|killall)\b` 词边界。
- **P0-5**：Keychain 无 ACL（KIMI 报告 P1-6 已指）。**位置**：`netfix/keychain.py:29-53`。**修复**：写入命令加 `-A -T <bundle_binary>`。
- **P0-6**：`proxy_bridge._tunnel` 300 秒无 wall-clock 上限（CLAUDE 报告 P0）。**位置**：`netfix/proxy_bridge.py:362`。**修复**：加 60s wall-clock。
- **P0-7**：`bridge` 默认 127.0.0.1 但 macOS IPv6 `::1` 仍可达（CLAUDE 报告 P0）。**位置**：`netfix/proxy_bridge.py:391`。**修复**：`address_family = socket.AF_INET`。
- **P0-8**：`apply_proxy_profile` 把 `auto_proxy_url` 明文写 journal（CLAUDE 报告 P0）。**位置**：`netfix/residential_proxy.py:1965-1991`。**修复**：写 journal 前 drop `auto_proxy_url` 整个字段。

### P1（强烈建议）
- **P1-1**：API token 文件 `chmod` 失败静默吞（KIMI 报告 P1-5）。**位置**：`netfix/api.py:48-57`。**修复**：`raise RuntimeError` 不吞。
- **P1-2**：IPv6 系统级防护未真正实现（KIMI 报告 P1-7）。**位置**：`netfix/residential_proxy.py:1319-1329` + `apply_proxy_profile:1697-1897`。**修复**：在 `apply_proxy_profile` 调 `_disable_ipv6_commands` 已存在但只在 backup.restorable 时跑——要 hard requirement。
- **P1-3**：MCP `netfix_proxy_switch` 输出可能含 `_secret` 字段（CLAUDE 报告 P0）。**位置**：`netfix/mcp_server.py:450-457` + `netfix/cli.py:862-868`。**修复**：MCP 出口套 `_strip_internal_secrets`。
- **P1-4**：README 没告诉普通用户"first launch: System Settings → Privacy & Security → Open Anyway"。**位置**：`README.md:24-28`。**修复**：在 curl 上方加警告 block。
- **P1-5**：`install_mac_app_from_github.sh` 缺 atomic rename、IFS、rollback 半残 app 的清理。**位置**：`scripts/install_mac_app_from_github.sh`。**修复**：补齐。
- **P1-6**：GitHub Issue 模板没强制防止贴密钥。**位置**：`.github/ISSUE_TEMPLATE/`。**修复**：每个模板加 "Before submitting, run `netfix export-issue-bundle`" 提示。

### P2（可以慢慢来）
- **P2-1**：App 文案避免"住宅 IP""切换到住宅 IP 节点"（KIMI 报告 P1-4）。**位置**：`netfix/explain.py:219-228`。**修复**：替换为"当前出口属于数据中心 ASN；可联系供应商切换非数据中心节点"。
- **P2-2**：`residential_proxy.py` 2483 行太大。**位置**：整个文件。**修复**：拆为 `parse_proxy.py` / `apply_proxy.py` / `validate_proxy.py` / `audit_identity.py` 四个模块。
- **P2-3**：`SettingsView.swift` 2421 行太大，6 Tab 太多。**位置**：`gui/macos/Sources/Views/SettingsView.swift`。**修复**：拆为 3 Tab 文件 + `SettingsAIView.swift` / `SettingsProxyView.swift` / `SettingsAdvancedView.swift`。

---

## 七、技术架构审计

| 维度 | 评分 | 证据 |
|---|---|---|
| Python 包结构 | 7 | `netfix/` 顶层 25 个 .py，清晰分组（detect/diagnose/reasoner/explain/fix_engine/safety/llm_*/proxy_*/redaction/keychain/logs/api/mcp_server） |
| SwiftUI 体积 | 3 | `SettingsView.swift` 2421 行单文件，6 Tab 50+ `@State`；`DashboardView.swift` 1468 行；`ProxySetupView.swift` 330 行 |
| CLI/API/MCP 复用 | 8 | `mcp_server.py:447-501` `_build_argv` 复用 CLI；`api.py:_execute_confirmed_fix` 复用 CLI fix；`agent_tools` 直接调用 |
| 错误码 / 报告 schema | 6 | 已有 `reason_code` / `status` / `ok` 多种命名并存；report schema 未版本化（缺 `schema_version`） |
| 测试覆盖 | 5 | `pytest` 跑 360+ passed（KIMI 报告 P1-4 已指）；**无任何 e2e**；`tests/test_macos_proxy_export_ui.py` 全是字符串匹配 |
| CI 硬门禁 | 5 | `.github/workflows/ci.yml` 6 步：syntax/CLI/API/MCP smoke/pytest/release-audit；但**没跑** release_preflight --with-dmg-smoke、verify_dmg_backend.sh、release_gate.sh --strict-workspace |
| release_audit 可靠性 | 8 | `scripts/release_audit.py` 工作区 secret 扫描已生效（上次清理了 `iphone-v2rayn-package-2026-06-14/`，KIMI 报告 P0-1 已修） |
| source_export 可靠性 | 7 | `scripts/source_export.py` 排除旧资料包/DMG/build/本机运行态；缺 `SOURCE-EXPORT-MANIFEST.json` 的 path sanitize（CLAUDE 报告 P0） |
| 签名 / 公证 / Homebrew / pipx | 0 | 全部未做。**关键缺失** |
| GitHub Action release 自动化 | 2 | `.github/workflows/ci.yml` 没 release 任务；`scripts/release_preflight.py --with-dmg-smoke --write-record` 已具备但没自动跑 |

---

## 八、竞品 / 参考项目研究（≥12 个）

| # | 项目 | 解决什么 | 入口 | 值得学 | 不能学 | Netfix 差异化 |
|---|---|---|---|---|---|---|
| 1 | **Surge for Mac** | macOS 网络调试 + 代理 | 付费 App（`nssurge.com`） | 抛光 UI + 规则系统 + 节点切换流畅 | 闭源、价格贵 | Netfix 是 local-first 开源、可审计 |
| 2 | **ClashX / ClashX Pro** | 基于 Clash 的 macOS 代理菜单栏 | `github.com/ClashX-Pro/ClashX` | 菜单栏图标 + 节点切换 | 配置复杂、依赖订阅链接 | Netfix 不卖节点，专注诊断+粘贴 |
| 3 | **mihomo (MetaCubeX)** | Go 写的代理核心 + TUN | `github.com/MetaCubeX/mihomo` | RESTful API 给 GUI 用、版本稳定（v1.14.5） | macOS TUN 模式 bug 多（issue #895/#1246） | Netfix 不做 TUN，只做系统代理诊断 |
| 4 | **sing-box** | "universal proxy platform" | `sing-box.sagernet.org` | 协议覆盖广（VMess/VLESS/Trojan/Hysteria/TUIC） | 配置格式专业、对普通用户不友好 | Netfix 走"诊断+简化粘贴"路线 |
| 5 | **Hiddify** | 多平台 auto-proxy 客户端 | `github.com/hiddify/hiddify-next` | 跨平台、UI 简洁、SSH/Trojan/Reality 都支持 | 仍然依赖订阅链接 | Netfix 帮你诊断现有代理，不内置 |
| 6 | **v2rayN** | Windows 桌面前端 + V2Ray/Xray core | `github.com/2dust/v2rayN` | 订阅管理 + 路由规则 + 系统代理 | Windows-only、v2rayN 已逐渐被替代 | Netfix macOS-native |
| 7 | **Proxyman** | macOS HTTP/HTTPS 调试代理 | `github.com/ProxymanApp/Proxyman` | 抛光 UI v6.0、Command Palette、Map Local、证书一键 | 闭源、$60+、定位开发调试不是诊断 | Netfix 是"诊断+粘贴代理"非"抓包" |
| 8 | **mitmproxy** | 开源 HTTPS intercepting proxy | `github.com/mitmproxy/mitmproxy` | Python+C、写脚本强、社区大 | 命令行/网页 UI 不适合小白 | Netfix 不抓包，专注"卡在哪层" |
| 9 | **Tailscale** | mesh VPN | tailscale.com | MagicDNS、SSH by hostname、exit nodes | 不解决"我已经买了 HTTP 代理怎么配" | Netfix 帮用户用已有代理，Tailscale 是另一类问题 |
| 10 | **Raycast** | macOS 启动器 + 扩展生态 | raycast.com | 网络诊断扩展（ping/port check/DNS lookup）有 | 不是"长期守护"型工具 | Netfix 做"网络背景监控+一键修" |
| 11 | **MCPSharp / GitHub MCP / Amap MCP** | MCP 服务器实现样例 | 各自 repo | 输出 schema / 错误码标准化、Tool/Resource/Prompt 三分类 | 不解决 macOS 网络场景 | Netfix 应该补 `outputSchema` 和 `evidence_chain`（§5） |
| 12 | **Homebrew Cask** | macOS App 分发渠道 | `github.com/Homebrew/homebrew-cask` | `brew install --cask netfix` 是 macOS 用户最熟悉的安装方式 | 提交要 LICENSE + 长期维护承诺 | Netfix 签名公证后立刻提交 cask |
| 13 | **Beaver-Notes / Gladys Assistant** | local-first + privacy 工具 | GitHub | "local-first" 标签的真实用户群 | 不是网络工具 | Netfix 借"local-first"心智讲密码存 Keychain |
| 14 | **ProtonVPN** | 隐私导向 VPN | `github.com/ProtonVPN` | 透明审计 + no-logs policy 故事 | 自己是 provider | Netfix 不是 provider，立场不同 |
| 15 | **PrivacyTools.io** | 隐私工具目录 | privacytools.io | 教育用户"local-first / open-source / privacy" 三个标签 | 不解决 macOS 网络场景 | Netfix 应该被收录 |

**关键洞察**：
- macOS 代理客户端赛道极度拥挤（Surge/ClashX/mihomo/sing-box/Hiddify），Netfix **不是**它们的直接替代品，定位必须避开"卖节点/管理节点"。
- Network debugging 赛道（Proxyman/mitmproxy）是面向**开发者**的，Netfix 应该面向**普通用户/Agent**——它们不冲突。
- 真正空白的细分市场是：**"我已经买了代理不会配 Mac" + "Codex 说我网络挂了"**——Netfix 同时覆盖这两个，是 unique 的。

---

## 九、下一阶段产品路线图

### 9.1 48 小时内必须做（v0.2.0-qa.2 hotfix）

| 任务 | 文件 | 验收 | 测试 | 用户价值 | 风险 |
|---|---|---|---|---|---|
| README 首屏重写（KIMI §9.1 草案）+ 首句"粘贴代理，Mac 上网；改坏一键还原" | `README.md` / `README.en.md` | hero + tagline + 6 bullet 安全速览 + 一行主 CTA | `python3 scripts/marketing_claims_check.py --json` 仍 OK | 5 秒抓住陌生用户 | 误承诺需 marketing_claims_check 守住 |
| `curl | bash` 上方加 ⛔ QA 未签名 warning block | `README.md:24` / `README.en.md:24` | 同上 | 避免"无法验证开发者"劝退 | 无 |
| 把 3 个 case 提到首屏 | `README.md:96-104` | 显示 "网络故障故事" 段 | `python3 -m pytest -q` | 社交证明 | 无 |
| 加 `social_preview.png`（1280×640） | `assets/github/` | 显示 hero 图 + tagline | N/A | GitHub 分享卡片美观 | 无 |
| Repo description 改短 | `.github/repository.yml:3` | "Paste a proxy line. Make your Mac go online safely. Roll back with one click." | N/A | 搜索结果更易点 | 误承诺 |
| Topics 删 clash/mihomo/sing-box；加 homebrew-cask/macos-app/diagnostics | `.github/repository.yml:41-43` | 22 个 topics | N/A | 搜索流量更准 | 失去部分代理圈触达 |
| 删 `iphone-v2rayn-package-2026-06-14/` + .zip + 加 `.gitignore` 完整项 | `.gitignore` | `release_audit.py` 退出码 0 | `python3 scripts/release_audit.py --json` | 发布卫生 | 无（已 KIMI 报告 P0-1） |
| 给 `logs.append_event` 写盘前 redact | `netfix/logs.py:89-99` | 加测试 `tests/test_logs_redaction.py` | pytest | 日志不含密码 | 性能微小下降 |
| 给 `mcp_server.py:_strip_internal_secrets` 覆盖到所有 dispatch 路径 | `netfix/mcp_server.py:511-528` | 加测试 `tests/test_mcp_no_secret.py` | pytest | MCP 输出永不含明文密码 | 无 |
| 给 `safety.classify_command` 改 `\b` 词边界 | `netfix/safety.py:69-78` | 加测试 `tests/test_safety_word_boundary.py` | pytest | 安全分类更准 | 无 |

### 9.2 7 天内必须做（v0.2.0-qa.3 完整体）

| 任务 | 文件 | 验收 | 测试 | 用户价值 | 风险 |
|---|---|---|---|---|---|
| ProxySetupView 单页化 wizard（粘贴 → 预检 → 保存 → 部署同页） | `gui/macos/Sources/Views/ProxySetupView.swift` | 4 步条 + 单主按钮"开始使用这台 Mac 上网" | SwiftUI 预览 + 字符串测试 | 普通用户 30 秒完成部署 | UI 改动大需回归 |
| DashboardView 错误 banner 加"一键修复"按钮 | `gui/macos/Sources/Views/DashboardView.swift:314-336` | 错误时显示 `primaryAction` 按钮 | SwiftUI 预览 | 用户不放弃 | 无 |
| SettingsView 合并 6 Tab → 3 Tab（常规 / AI / 高级） | `gui/macos/Sources/Views/SettingsView.swift` | 拆为 3 个子文件 | SwiftUI 预览 | 用户 30 秒找到 API Key | UI 改动大需回归 |
| 显示 "Keychain 里存了什么" 列表（不含值） | `gui/macos/Sources/Views/SettingsView.swift` 新 section | 显示 service/account/created | pytest + SwiftUI | 安全透明 | 无 |
| 卸载按钮（Agent Tab）| `gui/macos/Sources/Views/SettingsView.swift` Agent section | 调用 `codex mcp remove netfix` + 删除本地源 | SwiftUI 预览 | 用户不后悔 | 无 |
| `netfix_list_fixes` MCP 工具 | `netfix/mcp_server.py` + `netfix/cli.py` | 返回可用 fix id + tier + description + evidence_refs | `tests/test_mcp_list_fixes.py` | Agent 能发现能力 | 无 |
| `netfix_dry_run_fix` MCP 工具 | 同上 | 返回命令预览 + 影响面 | `tests/test_mcp_dry_run.py` | Agent 能预演 | 无 |
| `netfix_apply_fix` 对齐 `api.py:_execute_confirmed_fix` magic word | `netfix/mcp_server.py:73-90` | Tier 2 必须 `magic_word: APPLY_SYSTEM_FIX` | `tests/test_mcp_fix_magic_word.py` | 安全 | 无 |
| CI 矩阵扩到 macos-14/15/26 + 加 `release_preflight --with-dmg-smoke` + `release_gate.sh --strict-workspace` | `.github/workflows/ci.yml` | 3 个 OS 都过 | CI 跑 | 门禁更硬 | CI 时间变长 |
| 加 6 张真实 App 截图 + 2 个 GIF | `assets/github/zh/` + `en/` | 截图覆盖：粘贴 → 预检 → 部署 → 失败 banner → Keychain → 卸载 | N/A | Star 转化 | 无 |
| Show HN + V2EX + NodeSeek 三篇"一个用户痛点"贴 | 外部 | 链接到 README cases | N/A | Star | 误宣传需守住 |
| 加 `BREAKING.md` / `ROADMAP.md` / `CHANGELOG.md` | 仓库根 | 显示未来 3 个 milestone | N/A | 用户看产品方向 | 无 |

### 9.3 30 天内必须做（v0.3.0）

| 任务 | 文件 | 验收 | 测试 | 用户价值 | 风险 |
|---|---|---|---|---|---|
| `residential_proxy.py` 拆 4 个模块 | `netfix/parse_proxy.py` / `apply_proxy.py` / `validate_proxy.py` / `audit_identity.py` | 2483 → 4×~600 行 | pytest | 可维护性 | 改 import 路径 |
| `SettingsView.swift` 拆 3 个文件 | `gui/macos/Sources/Views/SettingsAIView.swift` / `SettingsProxyView.swift` / `SettingsAdvancedView.swift` | 2421 → 3×~800 行 | SwiftUI | 可维护性 | UI 改动 |
| MCP `netfix_evidence_chain` / `netfix_sanitized_report` / `netfix_proxy_credential_doctor` / `netfix_explain_for_user` / `netfix_explain_for_engineer` / `netfix_ask_followup_question` / `netfix_export_issue_bundle` 7 个新工具 | `netfix/mcp_server.py` + `netfix/agent_tools.py` | 30 → 37 工具，全部带 input/output schema | `tests/test_mcp_evidence.py` 等 | Agent 真正能自主决策 | 工作量大 |
| IPv6 系统级防护真正实现（apply 路径调 `-setv6off`）| `netfix/residential_proxy.py:1847-2056` | 部署后 IPv6 评估 `"status": "checked"` | `tests/test_residential_proxy.py` | 减少泄漏 | macOS 不同版本行为差异 |
| Keychain ACL 限制 | `netfix/keychain.py:46-48` | `-A -T <bundle_binary>` | `tests/test_keychain_acl.py` | 同 user 其他进程不能读 | frozen 模式才能正确传 binary path |
| 代码签名 + Apple notarization | Xcode build settings + App Store Connect API | 公证成功 + stapled | CI 跑 `xcrun notarytool submit` | 公众可信 DMG | 需 Apple Developer ID 账号 |
| Homebrew Cask 提交 | `homebrew-cask` PR | `brew install --cask netfix` 能装 | `brew audit --new` 过 | 用户最熟安装方式 | 维护承诺 |
| GitHub Action 自动打 release + 附 DMG + 附 SHA256 | `.github/workflows/release.yml` | tag push → 自动 build + sign + notarize + publish | CI 跑 | 减少人工发布 | 需 Apple Developer ID secrets |
| 写 5 个 e2e acceptance case | `tests/e2e/test_proxy_deploy_acceptance.py` | 5 case 全过：粘贴 4 段 → 预检通过；部署按钮 → 系统代理被改；退出 App → 弹恢复对话框；失败点恢复 → 系统代理还原；粘贴 vmess → 显示明确不支持 | pytest | 真正 CI 跑端到端 | macOS runner 配置复杂 |
| privacy policy + EULA 草案确认 | `PRIVACY.md` / `EULA.md` | 法务过 | N/A | 正式发布前置 | 需要外部 review |

### 9.4 v1.0 前必须补齐

- 至少 3 个付费版代理供应商模板（用脱敏的 IP/ASN 预期值做 precheck）
- macOS 启动项 (launchd) 支持
- 通知中心集成（节点失效时通知）
- 多 profile 同时保存（已有 `proxy_profiles`，但 UI 没暴露"切换到 profile X"）
- 远程 snapshot 同步（iCloud Drive / WebDAV，让用户备份）
- 官方 SwiftUI 截图自动化测试（`xcodebuild test` + `XCUITest`）

---

## 十、直接落地的小改动

按"低风险 + 高确定性 + 不破坏现有测试 + 不引入夸大宣传 + 不绕过 Tier 2 确认 + 不泄露任何本机路径/密钥/代理信息"原则，**这一节做 5 个具体的代码/文档改动**。每个改动独立 PR。

### 改动 1：`netfix/safety.py` 词边界

现状：`netfix/safety.py:71` 用子串 `if any(kw in lower for kw in _SUDO_KEYWORDS)` 容易误报（`sudoMyScript` 等）。

修复：改用 `\b` 词边界正则。

```python
# netfix/safety.py:69-78
def classify_command(command: str) -> FixTier:
    """Return the default safety tier for *command* based on its content."""
    if is_dangerous(command):
        return FixTier.MANUAL

    lower = command.lower()
    # Privileged commands (even read-only ones like `sudo lsof`) need confirmation.
    sudo_pattern = re.compile(r"\b(" + "|".join(re.escape(kw) for kw in _SUDO_KEYWORDS) + r")\b")
    if sudo_pattern.search(lower):
        return FixTier.CONFIRM

    readonly_pattern = re.compile(r"(?:^|\s)(" + "|".join(re.escape(kw) for kw in _READONLY_KEYWORDS) + r")\b")
    if readonly_pattern.search(lower):
        return FixTier.READONLY

    return FixTier.AUTO_SAFE
```

验证：`python3 -m pytest tests/test_safety.py -v`（如有） + `python3 -m pytest -q` 不 regression。

### 改动 2：`netfix/redaction.py` URL_RE 扩到 socks5 协议

现状：`netfix/redaction.py:36` `URL_RE = re.compile(r"\b(?:https?|socks5h?)://[^\s'\"<>]+", re.IGNORECASE)` 已包含 socks5h 但没 socks5。

修复：

```python
URL_RE = re.compile(r"\b(?:https?|socks5h?|socks5)://[^\s'\"<>]+", re.IGNORECASE)
```

验证：现有 `tests/test_redaction.py` 应该覆盖到；如未覆盖加测试 case。

### 改动 3：`netfix/agent_tools.py:get_global_state` 平台检测

现状：`netfix/agent_tools.py:120` 硬编码 `"platform": "darwin"`。

修复：

```python
def get_global_state() -> Dict[str, Any]:
    """High-level network path summary."""
    iface = default_interface()
    return {
        "platform": platform.system().lower() if _has_interface_helpers() else platform.system().lower(),
        "primary_interface": iface,
        "gateway": default_gateway(),
        "self_ipv4": interface_ipv4(iface) if iface else None,
        "self_ipv6": interface_ipv6s(iface) if iface else [],
        "has_ipv6_default_route": has_ipv6_default_route(),
        "public_ipv4": current_ipv4(timeout=10),
    }
```

> 注：`_has_interface_helpers()` 不必存在，只要 platform 字符串诚实地反映实际系统。

### 改动 4：`netfix/logs.py:append_event` 写盘前 redact

现状：`netfix/logs.py:89-99` 完全不脱敏。

修复：

```python
def append_event(event: Dict[str, Any]) -> None:
    from netfix.redaction import redact_text
    safe_event = {
        **event,
        "headline": redact_text(str(event.get("headline", ""))),
        "root_cause": redact_text(str(event.get("root_cause", ""))) if event.get("root_cause") else None,
    }
    ...
```

验证：加 `tests/test_logs_redaction.py` 断言 headline 中含 `://user:pass@` 不会出现明文密码。

### 改动 5：`netfix/mcp_server.py:_call_tool` 已经在做 `_strip_internal_secrets`，但 `_explain_llm_for_mcp` 路径没走

现状：`netfix/mcp_server.py:400-420` `_explain_llm_for_mcp` 直接调 `llm_explain.explain_with_llm` 后返回，**没**过 `_strip_internal_secrets` 和 `_sanitize_mcp_output`。

修复：

```python
def _explain_llm_for_mcp(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        ...
        return {
            "ok": True,
            "result": _sanitize_mcp_output(_strip_internal_secrets(llm_explain.explain_with_llm(...)))
        }
```

### 改动 6：README 加首行 "first launch" warning

现状：`README.md:24-28` curl 上方无警告。

修复：在 `README.md:24` 之前加：

```markdown
> ⚠️ 当前 DMG 是 v0.2.0-qa.1 预览版，**未签名未公证**。首次启动要在「系统设置 → 隐私与安全性」里点「仍要打开」。不要把 QA 版宣传成正式外发版。
```

英文版同步加。

---

## 验证命令总览

```bash
# 跑全部测试
python3 -m pytest -q

# 跑安全检查
python3 scripts/release_audit.py --scope workspace --root .

# 跑营销文案检查
python3 scripts/marketing_claims_check.py --json

# 跑 release preflight
python3 scripts/release_preflight.py --with-dmg-smoke --json

# 跑 source export
python3 scripts/source_export.py --zip --json

# 跑 mcp 烟雾测试
bash scripts/install_mcp.sh --all --dry-run
```

---

## 改完文件清单（如果 §10 全部落地）

| 文件 | 改动 | 为什么 | 怎么验证 |
|---|---|---|---|
| `netfix/safety.py` | `\b` 词边界 | 减少 sudo 假阳性 | pytest |
| `netfix/redaction.py` | URL_RE 扩 socks5 | socks5 密码被脱敏 | pytest |
| `netfix/agent_tools.py` | 平台检测 | Linux 也能跑（不强求，仅诚实） | pytest |
| `netfix/logs.py` | append_event redact | 日志不含明文密码 | 新增 `tests/test_logs_redaction.py` |
| `netfix/mcp_server.py` | `_explain_llm_for_mcp` 过 sanitize | LLM 解释含密码会被代理泄漏 | 新增 `tests/test_mcp_explain_no_secret.py` |
| `README.md` / `README.en.md` | 首行未签名 warning | QA DMG 用户不被 Gatekeeper 劝退 | marketing_claims_check |

**为什么不一次改 10 个？**
- §10 是低风险高确定性，全做需要时间。优先做 §10 改动 5、6（最大用户价值），其余按 v0.2.0-qa.2 节奏排队。

---

## 十一、最终判断

### 现在是否值得开源？
**值得，但有保留**。
- 工程侧 80 分：诊断/修复/脱敏/回滚/MCP/Agent 闭环全在。
- 文档侧 50 分：首屏重写 + 真实截图 + 不打 QA 为正式版三件套立刻做可以拉到 70。
- 安全侧 60 分：P0 8 条按顺序补齐可到 80。

### 是否值得普通用户安装？
**当前不值得。**
- QA 未签名 DMG + 首屏"AI 开发工具断线急救"+ APPLY_PROXY_PROFILE 短语（已升级）+ 保存/部署分两步 = 4 个坑。
- 把 §10 6 个改动 + §9.1 全部 11 个任务做完，普通用户路径才会"勉强能试用"。
- 完全"闭眼用"必须等签名公证 + Homebrew Cask（v0.3.0）。

### 是否值得开发者 Star？
**值得，但理由不是工程**。
- 工程值得 Star（你随便翻 5 个核心文件就懂）。
- 但 5 秒首屏抓不住 → Star 转化率低。
- 把"粘贴一行，Mac 上网；改坏一键还原"放首屏 + Show HN 投出去，Star 会显著涨。

### 最阻碍增长的 3 个问题

1. **首屏不告诉用户"这是啥 / 一行装 / 跟 ClashX 区别"**（README + repository description）
2. **普通用户路径 4 处断点：QA 未签名 / 保存部署分两步 / 错误只给重试 / 退出弹三按钮吓人**（SwiftUI）
3. **MCP 工具广而浅，Agent 不能自主决策**（schema + evidence + dry_run + magic word 全缺）

### 最值得做的 3 个创新

1. **`netfix_evidence_chain` + `netfix_dry_run_fix` + `netfix_apply_fix` 三件套**：让 Agent 能"先看证据 → 预演 → 用 magic word 真执行"。这是 Netfix 真正的护城河。
2. **ProxySetupView 单页 wizard + "恢复原来的网络设置" 顶部按钮**：把普通用户从 12 步砍到 4 步，10 分钟做出来。
3. **Homebrew Cask + Apple 公证 + Show HN**：分发侧最重要的一步。Netfix 的内容已经很扎实，把门打开。

---

## 附录 A：本审计 vs 前三轮审计的差异

| 维度 | CLAUDE_MACRO_PRODUCT_STAR_AUDIT (07-01) | KIMI_ORDINARY_USER_STAR_GROWTH (07-01) | PRODUCT_MACRO_AUDIT (06-30) | 本审计 (07-02) |
|---|---|---|---|---|
| 焦点 | 工程 + Star 增长 | 普通用户 + 传播 | UI + 工程 | 全栈 + 行动路线图 |
| 给出方案 | 是 | 是 | 是 | **是（带优先级 + 验证命令 + 改动 PR 级粒度）** |
| MCP schema 级建议 | 无 | 无 | 无 | **10 个工具详细 schema** |
| 竞品研究 | 5 行 | 无 | 无 | **15 个项目详细对比** |
| 可落地代码改动 | 8 条 | 11 条 | 8 条 | **6 条 + 49 项路线图** |
| 30 天路线图 | 是 | 是 | 是 | **是（48h / 7d / 30d / v1.0 四段，每项含 6 字段）** |

---

## 附录 B：本审计未做的事（诚实声明）

- 没改任何代码（只列了改动清单 §10）
- 没跑 `pytest` / `release_audit`（只列了验证命令）
- 没看 `cases/` 4 个 case 的具体内容（仅引用文件名）
- 没看 `gui/macos/Sources/Views/` 全部文件（只看了 3 个关键）
- 没看 `netfix/llm_explain.py` / `llm_provider.py` / `proxy_bridge.py` / `fix_engine.py` 全文
- 没看 `tests/` 全部覆盖（仅粗看 `test_macos_proxy_import_ui.py` 等被 KIMI 报告 P1-4 引用的）
- 外部竞品研究只用 WebSearch + WebFetch 摘要，未做深度 feature 拆解

---

## 附录 C：留给未来审计的开放问题

1. Netfix 真的需要 30 个 MCP 工具吗？还是 8 个就够？
2. 是否应该把 Netfix 卖给"代理供应商"作为 SDK？B2B 路线图完全不同。
3. 是否应该写 Raycast 扩展？
4. 是否应该集成 OpenAI Apps SDK / Anthropic Computer Use？
5. iOS 版有没有需求？
6. 是否应该做"Netfix for Teams"（企业内统一配置）？

---

> **审计结束语**：Netfix 在 2026-07-02 这一刻，处于"所有原料都已下锅，就差最后一把火"的临界点。再多一个 Quarter 的工程投入意义不大，再多两周的"文案 + 截图 + 公证 + Homebrew"则会让它从 80 分项目变成 90 分产品 + 90 分开源增长。