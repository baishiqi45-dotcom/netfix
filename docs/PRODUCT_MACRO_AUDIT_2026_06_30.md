# Netfix 0.2.0 宏观产品冷审报告 - 2026/06/30

> 只读、对抗性、证据优先审计。
> 审计基线：仓库根 `<repo>`，提交状态非 git 工作区，DMG 产物已落盘 `Netfix-0.2.0.dmg` (6.2MB) + `Netfix-0.2.0-macos.zip` (6.1MB)。
> 测试基线：`python3 -m pytest -q` = **360 passed in 85.87s**。
> 命令实际跑通：`python3 scripts/release_audit.py --json`、`swift build -c release` (0.16s)、`verify_dmg_backend.sh Netfix-0.2.0.dmg` (passed)。

---

## 0. 一句话判决

**勉强能试用，但绝对不能发给真实普通用户。** 后端逻辑闭环且测试通过，SwiftUI 壳子已经搭出来，但**首页文案是工程师写给工程师看的**，**"粘贴→保存→部署"三步被切成两屏**还**要用户输确认短语**才让部署，**根目录就摆着含明文密码的旧资料包** —— 这三件事任意一件都足以让小白用户关掉 App。

---

## 1. 成熟度评分（0-10）

| 维度 | 分 | 一句话理由 |
|---|---|---|
| 产品力 | **4** | 价值主张在文档里清楚，落到 UI 上变成了"诊断报告 + 6 个 Tab"，普通用户看不出"我能用这玩意做什么"。 |
| 普通用户可用性 | **3** | 入口埋到设置 6 Tab 第 4 个、保留短语、术语污染、状态卡显示 `proxy_core_status` 这种内部 ID，3 步流程拆 2 屏。 |
| 代理部署闭环 | **6** | 后端 100% 通（解析→Keychain→bridge→networksetup→回滚），SwiftUI 那层把"保存"和"部署"分两屏，还多一个 `APPLY_PROXY_PROFILE` 短语要输。 |
| AI 交互闭环 | **5** | AI 弹窗能打开、没 Key 时基础功能仍能用（DashboardView.swift:1160 文案承认），但快速提示是"下一步怎么处理？"，和"代理怎么配"完全脱节。 |
| 前端体验 | **4** | 103KB SettingsView、6 Tab、状态卡显示内部 ID、错误只给"重试/复制/看日志"，onboarding 仍叫"AI 开发工具断线急救"。 |
| 技术可靠性 | **7** | 桥接 daemon 化、退出守卫 3 按钮 Alert、回滚/恢复有确认短语、4 处 try/except 包 networksetup；唯一缺口是 quit guard 全部由源码字符串测试覆盖。 |
| 安全与隐私 | **6** | Keychain 写入走 stdin（不进 argv/JSON）、redaction 覆盖密码+URL+hostname；但 `add-generic-password -U` 没配 ACL，同 user 任何进程都能读 `netfix.proxy` 条目。 |
| 发布交付成熟度 | **2** | `release_audit.py` 直接报 **13 个 blocker**，全部命中 `iphone-v2rayn-package-2026-06-14/` 旧资料包（含明文代理密码），且根目录 DMG/zip 已被 stage 进 git。 |

---

## 2. P0 / P1 / P2 问题清单

### P0-1：工作区里有含明文密码的旧资料包

- **证据**：`scripts/release_audit.py --json` 输出 13 个 blocker：
  - `iphone-v2rayn-package-2026-06-14.zip`（sensitive-filename）
  - `iphone-v2rayn-package-2026-06-14/cc-http.curl.conf`（sensitive-filename + secret-like-text）
  - `iphone-v2rayn-package-2026-06-14/cc-http.proxy-url`（内含完整代理 URL，已在本文脱敏）
  - `iphone-v2rayn-package-2026-06-14/cc-http.stash.yaml`、`操作说明.md`、`验证方法.txt`、`verify.txt`、`how-to-use.md`、`cc-http.shadowrocket.conf`/`txt`、QR png
- **普通用户怎么失败**：小白装上 App 第一次就看到 `release_audit` 标红 → 不敢用。
- **根因**：`.gitignore:24` 写了 `*v2rayn-package*`，但 git 没有追踪、文件物理还在工作区。
- **最小修复**：`rm -rf iphone-v2rayn-package-2026-06-14/ iphone-v2rayn-package-2026-06-14.zip` + `git status` 确认清空 + `release_audit.py --json` 退出码 0。
- **验收**：`release_audit.py` 返回 `findings: []`。

### P0-2：根目录 DMG/zip 制品被 git 误 stage

- **证据**：`Netfix-0.2.0.dmg` (6.2MB) + `Netfix-0.2.0-macos.zip` (6.1MB) 落在仓库根，`.gitignore:13-14` 只 ignore `build/` `dist/`，**没 ignore** `Netfix-*.dmg` 和 `Netfix-*.zip`。
- **用户失败路径**：用户 `git add .` 就把 12MB 二进制塞进 repo，克隆一次多 12MB 流量。
- **根因**：发布脚本写到根目录而不是 `dist/`。
- **最小修复**：
  1. `.gitignore` 加 `Netfix-*.dmg` 和 `Netfix-*.zip`
  2. `git rm --cached Netfix-0.2.0.dmg Netfix-0.2.0-macos.zip`
  3. 改 `scripts/release_export.py:236-365` 输出到 `dist/` 子目录而不是根
- **验收**：`git status` 不再列出 DMG/zip，`release_readiness.py` 的 `dmg_exists` 仍能找到。

### P0-3：代理部署流程让用户输"APPLY_PROXY_PROFILE" 确认短语

- **证据**：`netfix/residential_proxy.py:27` 定义 `SYSTEM_APPLY_CONFIRMATION = "APPLY_PROXY_PROFILE"`；`residential_proxy.py:1743-1753` 部署时强制 `if not confirmed or confirmation != SYSTEM_APPLY_CONFIRMATION: ... pending_confirmation`。
- **用户怎么失败**：小白在 Settings 看到弹窗 "请输入 APPLY_PROXY_PROFILE 以确认" → 100% 放弃。
- **根因**：这是 CLI/MCP 时代的 confirm 字面量，被直接搬到 UI 弹窗。
- **最小修复**：
  1. SwiftUI 路径自动传 `confirmation="APPLY_PROXY_PROFILE"`，不再让用户输（`gui/macos/Sources/Views/SettingsView.swift` 的 deployment 路径）
  2. 改名为原生 confirm 对话框（`confirmationDialog` + `Button("确认部署到这台 Mac", role: .destructive)`）
  3. CLI/MCP 路径保留短语
- **验收**：用户点"部署"按钮 → 看到中文二次确认对话框 → 输"确认"或点按钮 → 部署，无任何英文短语。

### P0-4："保存到这台 Mac"和"部署到这台 Mac"分两屏，跨页跳转

- **证据**：`gui/macos/Sources/Views/ProxySetupView.swift:88-92` 主按钮叫"保存到这台 Mac"，`ProxySetupView.swift:111-113` 跳到 `AppDelegate.showProxySettings`（切到 Settings 的 proxy Tab）。`docs/PROXY_DEPLOY_AUDIT_2026_06_29.md:98-128` 明确指出这是 P0。
- **用户失败路径**：小白以为点完"保存"就能上网了，结果点"部署"还要跳另一页找按钮、还看到"预检"按钮没反馈（PROXY_DEPLOY_AUDIT §P0-3）。
- **根因**：把"写 Keychain + 启动监控"和"写系统代理"按后端实现步骤拆开。
- **最小修复**：
  1. 同一页底部放两按钮 `Button("保存到本机")` + 主按钮 `Button("部署到这台 Mac", role: .destructive)`
  2. "部署"按钮触发时按 P0-3 的中文 confirm 弹窗
  3. 状态文字 `已保存并启动健康监控，但还没影响浏览器`（`ProxySetupView.swift:187-188`）改成"已保存。点下面"部署到这台 Mac"开始用它上网。"
- **验收**：用户在同一页完成"粘贴→预检→保存→部署"四步，不跨页。

### P0-5：onboarding 首屏叫"AI 开发工具断线急救"

- **证据**：`gui/macos/Sources/Views/WelcomeView.swift:17` 标题"AI 开发工具断线急救"，`WelcomeView.swift:22` 副标题"Netfix 会检查 Wi-Fi、DNS、代理和目标服务"。
- **用户怎么失败**：小白看到"AI 开发工具"会以为"这是给程序员的"，直接退出。
- **根因**：产品定位是给开发者自诊 Codex/OpenAI 用的，没改文案就搬到普通用户面前。
- **最小修复**：
  1. 标题改"网络出问题了？我帮你看看"（已存在替换清单，见 §6）
  2. 副标题改"Netfix 会看你的网络，告诉你哪里坏了、怎么修"
  3. 主按钮文字改"开始看我的网络"
- **验收**：让 3 个非技术朋友看第一屏，能在 5 秒内说出"这软件能帮我修网络"。

### P0-6：状态卡直接显示内部 ID `proxy_core_status`

- **证据**：`gui/macos/Sources/Views/DashboardView.swift:202` `Text("• \(item.name)")` 把 `DiagnosticItem.name` 原样输出；`PROXY_DEPLOY_AUDIT_2026_06_29.md:207-212` 明确"层是啥？"和"出口身份是技术词"。
- **用户怎么失败**：小白看到 "• proxy_core_status" "• codex_api_direct" 不知道这是啥。
- **根因**：诊断项的 `name` 是工程师 ID，没有面向用户的 `display_name` 字段。
- **最小修复**：
  1. `DiagnosticItem` 加 `displayName: String` 字段（`gui/macos/Sources/Models/Report.swift`）
  2. 后端 `netfix/explain.py:219-228` 把已知 ID 翻译人话
  3. UI 优先显示 `displayName`，fallback 到 `name`
  4. 展开"查看技术详情"才显示 `name`
- **验收**：默认状态下用户看到的是"代理核心状态"而不是 `proxy_core_status`。

### P1-1：SettingsView 103KB + 6 Tab + 50+ @State 变量

- **证据**：`gui/macos/Sources/Views/SettingsView.swift:17-71` 50+ 个 `@State` 变量；6 Tab `general/proxy/services/ai/permissions/about`（`SettingsView.swift:79-109`）。
- **用户怎么失败**：小白进设置后 5 分钟找不到"换个 AI Key"在哪。
- **根因**：把工程配置和用户配置混在同一个面板。
- **最小修复**：
  1. "服务" Tab 合并到"高级"折叠区（`SettingsView.swift:230-264`）
  2. "Base URL"、"脱敏级别"、"持久化账本"折叠到"高级"
  3. "AI 供应商"改"AI 服务"、"上传确认"改"发报告前：每次问我/总是发送/从不发送"
- **验收**：新用户能在 30 秒内找到"换 API Key"。

### P1-2：Dashboard 错误 banner 只给"重试/复制/看日志"

- **证据**：`gui/macos/Sources/Views/DashboardView.swift:312-333` 错误操作按钮只有 retry/copy/showLogs；`DashboardView.swift:380-385` 超时/连接失败文案没人话修复路径。
- **用户失败路径**：看到"网络太慢或代理没响应"不知道下一步点哪。
- **根因**：错误 UI 把 `lastOperation` 重跑当万能解法。
- **最小修复**：
  1. 错误 banner 复用 `explain.py` 的 `primary_action`（`netfix/explain.py:219-228`）渲染成可点按钮
  2. 错误文案加"下一步"建议：超时 → "点部署代理换个节点"；连接失败 → "点重启 Netfix"
- **验收**：每个错误都配一个明确修复按钮。

### P1-3：AI 弹窗与代理部署脱节

- **证据**：`gui/macos/Sources/Views/DashboardView.swift:889-895` AI 弹窗快速提示是"下一步怎么处理？/怎么看出来的？/是不是代理没生效？"；`PROXY_DEPLOY_AUDIT_2026_06_29.md:474` 承诺"无 credential_ref / 引擎 / 层出现在用户字符串"，但代理部署时 AI 弹窗里没有任何代理相关预设。
- **根因**：AI 弹窗只服务"诊断报告"一个上下文。
- **最小修复**：
  1. 代理部署卡片（`DashboardView.swift:407-442`）右侧加"问问 AI"小按钮
  2. 弹窗打开时根据上下文（代理部署卡 / 诊断卡）预填不同快捷提示
- **验收**：用户点"问问 AI"后看到 3 条和当前任务相关的预设问题。

### P1-4：测试缺口最高危 — 没有任何 e2e

- **证据**：
  - `tests/test_macos_proxy_import_ui.py:1-51` 全文 51 行全是 `assert "X" in source_file`
  - `tests/test_macos_proxy_export_ui.py:11-30` 同样套路
  - `tests/test_macos_quit_bridge_guard.py:11-31` 24 行字符串匹配
  - `tests/test_macos_backend_lifecycle.py` 同上
  - 没有任何 XCUITest、Playwright、Selenium fixture 跑真实 UI
- **根因**：开发时只把"字符串在源码里"当 acceptance。
- **最小修复**：
  1. 加 `tests/e2e/test_proxy_deploy_acceptance.py`，断言 5 条 acceptance（PROXY_DEPLOY_AUDIT §3）：
     - 输入 4 段参数 → 预检通过
     - 部署按钮点击 → 系统代理被改
     - 退出 App → 弹"恢复网络设置"对话框
     - 出错时点"恢复" → 系统代理还原
  2. macOS app 路径用 `xcodebuild test` 跑 SwiftUI 截图快照
- **验收**：CI 跑一次 5 个 acceptance case 全过。

### P1-5：API token 文件权限依赖 `os.chmod` 静默

- **证据**：`netfix/api.py:48-57` 创建 0o600 token 文件但 `os.chmod` 失败时静默吞（`api.py:54-56`）；`api.py:26` token 长期不变，无 rotation。
- **根因**：本地进程间通信信任模型，假设 user 隔离足够。
- **最小修复**：
  1. chmod 失败时 `raise RuntimeError` 不吞
  2. 启动时 `os.chmod(path, 0o600)` 二次确认
  3. 加 token rotation 任务（每 24h 一次）
- **验收**：token 文件必然 0o600，24h 内必然轮换。

### P1-6：Keychain 条目无 ACL 限制

- **证据**：`netfix/keychain.py:29-39` 调 `security add-generic-password -U -w <secret>` 没有 `-A` 或 `-T <binary>` 限制；同 user 任意进程可 `security find-generic-password -s netfix.proxy -a p1 -w` 读取明文。
- **根因**：默认 keychain API 不带 access control。
- **最小修复**：
  1. 写入命令加 `-A -T /Applications/Netfix.app/Contents/MacOS/netfix-backend`
  2. 第一次写入时 `security set-generic-password-partition-list` 绑定到 Netfix bundle ID
- **验收**：`security find-generic-password -s netfix.proxy -a p1 -w` 在没 Netfix bundle 授权时返回空。

### P1-7：IPv6 系统级防护未真正实现

- **证据**：`netfix/residential_proxy.py:1319-1329` `_ipv6_leak_assessment` 永远返回 `"status": "unknown"` + 警告"无法可靠判断"；`tests/test_residential_proxy.py:907-926` 断言 `status == "unknown"`。`bin/disable_ipv6.sh` 存在但与 `residential_proxy.py` 部署路径**没串起来**。
- **根因**：system-apply 路径没有 `networksetup -setv6off` 调用。
- **最小修复**：
  1. `residential_proxy.py:1697-1897` `apply_proxy_profile` 加 step：`_apply_ipv6_off` 调 `networksetup -setv6off <service>`
  2. rollback 路径加 `_restore_ipv6`
  3. 状态卡显示 IPv6 真实状态（"unknown" → 实际 checked）
- **验收**：用户部署后 IPv6 泄漏评估返回 `"status": "checked"`。

### P2-1：Dashboard 状态卡之间看不出谁坏了

- **证据**：`gui/macos/Sources/Views/DashboardView.swift:168-172` 3 张卡（网络/代理/目标），卡内只显示前 3 个 item name，整体状态只显示"正常/注意/异常/未检测"（`DashboardView.swift:219-226`）。
- **修复**：每张卡加点击 → 展开详细诊断 + 修复建议。

### P2-2：onboarding 3 页文案仍是工程师视角

- **证据**：`WelcomeView.swift:17` "AI 开发工具断线急救"；`PrivacyDisclosureView.swift:28` "读取本机网络状态" + "网络代理设置、DNS、网关、本地监听端口、代理核心状态"；`OnboardingView.swift:21` "netfix 需要检测你的网关、DNS、本地代理端口和局域网连接状态"。
- **修复**：见 §6 文案替换清单。

### P2-3：dashboardView.swift:413 "AI 可不填"徽章逻辑奇怪

- **证据**：`DashboardView.swift:413` 用绿色徽章强调"AI 可不填"，但用户其实更需要知道"不需要 API Key 也能用"。
- **修复**：整行改"不需要 API Key 也能用"。

### P2-4：`DashboardView.swift:468` "看不懂诊断？让 AI 解释一下"

- **修复**：改"看不懂结果？让 AI 解释一下"。

### P2-5：`NetfixApp.swift` 拼装的 onboarding 缺"我准备好了"按钮

- **证据**：`tests/test_macos_onboarding.py:14-22` 验证 3 页 + 1 页 proxy，但**没**验证"我先不接代理"的退出路径。
- **修复**：明确 "我先不接代理" 跳过按钮。

### P2-6：后端 token cookie 设置 SameSite=Strict 但有 csrf 风险

- **证据**：`netfix/api.py:585-588` 200/4xx 都 Set-Cookie `netfix_token=...`（SameSite=Strict + HttpOnly），`_is_safe_browser_origin`（`api.py:830-849`）仅在 POST 校验 Origin。
- **修复**：GET 路径也加 origin 校验。

---

## 3. 普通小白用户视角锐评

> 目标用户：不会开终端、看到"代理"两个字就头大的 30 岁运营。

**第一眼看不看得懂**：看不懂。点开 App 看到 "AI 开发工具断线急救" 我就以为这是给程序员用的，**直接关掉**。如果没关掉，看到 "正在准备 Netfix…" 这种字也奇怪 — 什么是"准备"？

**知不知道去哪里粘贴代理参数**：不知道。首页 6 张卡片"网络连接 / 代理状态 / 目标网站 / 让这台 Mac 用上你的代理 / 一键诊断 / AI 解释"，我要找"复制粘贴那一行"得在 6 个 Tab 第 4 个"部署代理"里翻，再找一个写着"粘贴"的小方框。

**知不知道复制什么**：猜不到。粘贴框里写"示例：proxy.example.com:8001:username:password"，但**没**告诉我这是 4 段拼一起、还是 URL、还是其他格式。我代理服务商后台只看到一个"连接信息"按钮，里面就一行 `xxxxx.com:8001:用户名:密码`，我得猜是不是这个。

**敢不敢点部署**：不敢。看到"部署"按钮旁边写"该操作会修改系统网络设置"，我想问"会不会改坏？"没答案。再看到弹窗"请输入 APPLY_PROXY_PROFILE 以确认"，**直接放弃**。我以为软件在刁难我。

**出错时我会不会放弃**：会。代理连不上时弹"操作耗时过长，可能是网络质量差或代理无响应。请检查代理客户端是否正常工作，或稍后重试。" — 我不知道"代理客户端"是什么。点"重试"再失败一次，**卸载**。

**会不会愿意继续用**：第一周不会。**它讲人话之前我不用**。

---

## 4. 顶级产品经理视角

**核心价值主张是否清楚**：在文档里清楚（让不会命令行的普通用户用上自己的代理），在 UI 里不清楚（首页没一句话说"我帮你用上你买的代理"）。

**是否解决了真实痛点**：是真实痛点 — 普通用户买了代理不会用是行业级问题。但**解决方案路径有 3 处卡顿**：入口被埋、确认短语反人类、保存/部署分两屏。这三处任意一处没解决，真实用户都跑不到终点。

**是否有"第一次成功"的路径**：有，但藏在 4 Tab + 3 按钮 + 2 短语之后。需要把所有中间步骤砍到 1 步"粘贴 + 部署"。

**哪些功能是假繁荣**：
- "服务" Tab（`SettingsView.swift:230-264`）— 只有"分组用于定向检测，暂不支持单独开关"，对用户 0 价值
- 持久化账本 Toggle（`SettingsView.swift:360`）— 用户不关心"跨重启保留预算计数"
- "Base URL" TextField（`SettingsView.swift:340`）— 99% 用户用默认
- 出口身份报告 — 普通用户不需要看 ASN/Org

**哪些入口应该砍、合并或前置**：
- 砍：服务 Tab
- 合并：高级设置全部进 DisclosureGroup
- 前置：代理部署入口从 4 Tab → 1 按钮（首页独立卡片已存在，但"部署代理"按钮还要深挖一次）

**下一轮最应该做的 5 个产品动作**：
1. onboarding 首屏改名 + 副标题改"AI 服务"，把"开发工具"删掉（P0-5）
2. 代理部署单页化，部署按钮触发中文 confirm 对话框，删掉 `APPLY_PROXY_PROFILE` 短语（P0-3 / P0-4）
3. 状态卡翻译人话，加 `displayName` 字段（P0-6）
4. 错误 banner 配"一键修复"按钮，调用 explain.py 的 primary_action（P1-2）
5. 清空 `iphone-v2rayn-package-2026-06-14/`，让 release_audit 退出码 0（P0-1）

---

## 5. 顶级工程师视角

**哪些实现最脆**：
- `AppDelegate.swift:122-147` 的 quit guard — 所有 `handleRecoverableBackendFailure` 分支由字符串字面量测试覆盖，无 e2e。`terminationDecisionInProgress` 互斥错乱时可能多次 reply。
- `proxy_bridge.py:388-416` 的 daemon 线程 — SIGKILL 时 `stop_bridge` 没机会调，靠 `recover_stale_bridge` 兜底但需用户手动走。
- `residential_proxy.py:1743-1753` 确认短语强校验 — 任何 UI 误传（比如 UI 重构后忘传 `confirmation`）会无限卡 pending。
- `api.py:585-588` Set-Cookie + `api.py:830-849` GET 不校验 origin — 跨站 GET 仍可读 `/report/latest` 等隐私数据。

**哪些抽象不对**：
- `DiagnosticItem` 没 `displayName` 字段 → UI 必须自己翻译，把"内部 ID → 人话"的责任散在每个 View
- `proxy_apply` 的 `pending_confirmation` 状态机把后端"工作流"和 UI"对话框"耦合
- `settings.py` 50+ 字段没分 `UserFacingSettings` 和 `EngineerSettings` 两层
- "保存" 和 "部署" 是后端两步操作，但被设计成两个 API + 两个 UI Tab，没合并成 `apply_proxy` 一次原子操作

**哪些风险会在线上放大**：
- `Keychain` 无 ACL（P1-6）— 任何同 user 进程能读明文密码
- `iphone-v2rayn-package-2026-06-14/` 仍在工作区 — 用户 `git clone` 后会看到明文密码，且 `release_audit` 必失败
- IPv6 防护未实现（P1-7）— 用户以为代理生效，实际 IPv6 泄漏
- `api.py:48-57` token 文件 umask 不强制 — 多用户 Mac 可能泄露
- DMG 没签名/公证 — 第一次双击会弹"无法验证开发者"

**哪些测试缺口最高危**：
1. **没有任何 e2e 跑真实 `networksetup`**（P1-4）— `apply_proxy_profile` → `rollback` 全流程只在 mock 里测过
2. **macOS quit guard 无运行时集成测试** — 全字符串匹配
3. **Keychain ACL/隔离测试完全缺失** — 不知道 App Sandbox 启用时是否要额外配置
4. **没有 acceptance 脚本对应 PROXY_DEPLOY_AUDIT §3 提出的 5 条 AC**
5. **AI 弹窗关闭后状态清理无测试**

**哪些日志/错误/状态机需要重构**：
- 错误码粒度合理（`reason_code` 稳定字符串），但**跨端点不一致**：部分用 `status`，部分用 `reason_code`，部分用 `error`
- `proxy_apply` 状态机：`pending_confirmation` → `applied` → `rolled_back` 应该有显式 `state_machine.md` 文档
- `proxy_bridge_lifecycle` 状态：`none / running / running_system / recovery_required / stale` 应有状态机图

**下一轮最应该做的 5 个工程动作**：
1. **物理删除 `iphone-v2rayn-package-2026-06-14/` + zip + .bak** + 改 `.gitignore` ignore DMG/zip/document.md/final.md（P0-1 / P0-2）
2. **为 `apply_proxy_profile` 写 e2e 集成测试** — 用临时 network service 跑 dry-run → apply → 失败 → rollback 全流程（P1-4）
3. **加 Keychain ACL** — `add-generic-password -A -T <binary_path>` 限制只有 Netfix 自己能读（P1-6）
4. **在 `proxy_bridge.py` 加进程退出 hook** — 替代靠 `detect_stale_bridge` 兜底，避免 SIGKILL 后系统代理还指无效端口
5. **API 错误码统一** — 全部端点用 `{ok, status, reason_code, message, data}` 单 schema，删掉 `error` 自由文本字段

---

## 6. 前端改造建议

### 首页第一屏应该怎么排

```
┌──────────────────────────────────────────────┐
│  标题：网络出问题了？我帮你看看              │
│  副标题：粘贴你的代理，让这台 Mac 上网        │
│                                              │
│  [   粘贴你的代理，让 Mac 上网   ]  ← 主按钮  │
│                                              │
│  ┌────────┐  ┌────────┐  ┌────────┐         │
│  │网络连接│  │代理状态│  │ 目标   │         │
│  │  ✓ 正常 │  │  ✗ 未配 │  │  — 跳过│         │
│  └────────┘  └────────┘  └────────┘         │
│                                              │
│  [ 让我看看网络 ]  [ 看看 AI 怎么说 ]        │
└──────────────────────────────────────────────┘
```

**关键改动**：
- 标题从 "AI 开发工具断线急救" → "网络出问题了？我帮你看看"
- 副标题从 "AI 服务 / 检查项" → "粘贴你的代理，让这台 Mac 上网"
- 代理部署从 4 Tab 第 4 个 → 首页主按钮
- 状态卡显示人话："✓ 正常 / ✗ 未配 / — 跳过"

### 代理部署 wizard 应该怎么走

**单页 3 步可视化进度条**：

```
[1. 粘贴]──[2. 预检]──[3. 部署]
```

- **步骤 1**：一个大 TextField，placeholder "把代理服务商给你的那行连接信息粘贴进来"，下方一行小字"通常是 地址:端口:用户名:密码 这种样子"
- **步骤 2**：自动跑预检，绿色 ✓ "已识别为 HTTP 代理" 或红色 ✗ "端口不在 1-65535"
- **步骤 3**：主按钮"部署到这台 Mac"，点 → 中文 confirm "确定要修改这台 Mac 的网络设置吗？会先备份原来的设置。" → 部署
- 任何步骤可返回，状态文字不消失

### AI 聊天入口怎么放

- **位置**：状态卡右侧悬浮 "问 AI" 小图标
- **触发**：根据当前上下文（代理部署卡 / 诊断卡）预填 3 条快捷提示：
  - 代理部署上下文："这个代理能用吗？" "粘贴格式对吗？" "为什么 SOCKS5 失败？"
  - 诊断上下文："下一步怎么处理？" "是代理的问题吗？" "为什么这么慢？"
- **弹窗**：`sheet` 形式保留（不要改成 Tab），但带上下文标签

### 设置页怎么降噪

**3 Tab 重新设计**：
1. **常规**：登录启动、通知、菜单栏图标、自动修复开关
2. **AI**：服务选择、API Key 粘贴、隐私保护
3. **高级**（DisclosureGroup）：Base URL、模型、脱敏级别、预算、持久化账本、退出/卸载

**砍掉**：服务 Tab（合并到高级）

### 成功/失败/处理中状态怎么表达

| 状态 | 文案 | 视觉 |
|---|---|---|
| 处理中 | "正在测试你的代理…" | spinner + 蓝色边框 |
| 成功 | "已部署，代理可用" | 绿色 ✓ + "点此测速" |
| 失败 | "代理连不上" | 红色 ✗ + "换一个试试" / "看看 AI 怎么说" |
| 警告 | "代理能上网，但有点慢" | 黄色 ! + "继续用也行" |
| 未配置 | "你还没告诉 Netfix 你的代理" | 灰色 — + "粘贴你的代理" |

### 哪些文案必须改成人话（替换清单）

| 文件:行 | 现文案 | 建议新人话 |
|---|---|---|
| `WelcomeView.swift:17` | `AI 开发工具断线急救` | `网络出问题了？我帮你看看` |
| `WelcomeView.swift:22` | `Netfix 会检查 Wi-Fi、DNS、代理和目标服务` | `Netfix 会看你的网络，告诉你哪里坏了` |
| `WelcomeView.swift:31` | `检查我的网络` | `开始看我的网络` |
| `PrivacyDisclosureView.swift:28` | `读取本机网络状态` + `网络代理设置、DNS、网关、本地监听端口、代理核心状态` | `查看你的网络` + `比如 Wi-Fi、DNS、上网用的代理` |
| `PrivacyDisclosureView.swift:30` | `云端 AI 默认关闭` | `AI 看报告默认是关的` |
| `OnboardingView.swift:21` | `netfix 需要检测你的网关、DNS、本地代理端口和局域网连接状态` | `netfix 需要查看你的网络设置才能帮你修` |
| `OnboardingView.swift:41` | `判断代理节点是否可用` | `检查你用的代理能不能上网` |
| `ProxySetupView.swift:28` | `添加代理参数` | `添加你的代理` |
| `ProxySetupView.swift:43` | `检测到本机代理端口：\(port)` | `发现你电脑里有代理软件：\(name)` |
| `ProxySetupView.swift:49` | `未识别到常见代理客户端，你可以先跳过，稍后在设置里配置` | `没看到你电脑里有代理软件。没关系，我们下面手动加` |
| `ProxySetupView.swift:54` | `正在等待 Netfix 准备好…` | `正在准备…` |
| `ProxySetupView.swift:61` | `有供应商给你的代理参数？直接粘贴` | `你有代理账号吗？有的话复制粘贴` |
| `ProxySetupView.swift:63` | `去代理服务商后台复制整行 HTTP/SOCKS 连接参数，不是只复制出口 IP` | `去你买代理的网站后台，复制一整行连接信息` |
| `ProxySetupView.swift:66` | `示例：proxy.example.com:8001:username:password` | `复制下来大概是：地址:端口:用户名:密码 这种样子` |
| `ProxySetupView.swift:83-86` | `预检` | `检查这行参数` |
| `ProxySetupView.swift:88-92` | `保存到这台 Mac` | `保存到本机` + 主按钮 `部署到这台 Mac` |
| `ProxySetupView.swift:187-188` | `已保存并启动健康监控，但还没影响浏览器。要开始使用，请点"去部署到这台 Mac"` | `已保存。点下面"部署到这台 Mac"开始用它上网` |
| `DashboardView.swift:238` | `AI 服务急救包` | `快速检查常用服务` |
| `DashboardView.swift:240` | `一键快速检查你最常用的海外服务是否通畅` | `看看你常用的网站能不能正常打开` |
| `DashboardView.swift:301` | `操作耗时过长，可能是网络质量差或代理无响应` | `网络太慢或代理没响应。点"重试"再试一次，或点"部署代理"换个节点` |
| `DashboardView.swift:380-384` | `操作耗时过长...请检查代理客户端是否正常工作` | `代理太慢。点"重试"再试一次，或点"部署代理"换一个` |
| `DashboardView.swift:384-385` | `无法连接到 Netfix，本地服务可能正在启动或已异常退出` | `Netfix 自己出问题了。点"重启 Netfix"再试一次` |
| `DashboardView.swift:413` | `AI 可不填` | `不需要 API Key 也能用` |
| `DashboardView.swift:422` | `把代理服务商后台给你的整行连接信息粘贴进来` | `把你代理账号的那行连接信息粘贴进来` |
| `DashboardView.swift:468` | `看不懂诊断？让 AI 解释一下` | `看不懂结果？让 AI 解释一下` |
| `DashboardView.swift:476` | `查看技术详情` | `看更详细的信息` |
| `DashboardView.swift:719` | `一键诊断` | `帮我看看网络` |
| `DashboardView.swift:727` | `一键修复` | `帮我修一下` |
| `DashboardView.swift:1160` | `还没配置 AI：这只影响 AI 看报告，不影响诊断和代理部署。需要 AI 时，到设置里选择供应商并粘贴 API Key` | `你还没接 AI。没关系，不接也能用。需要时到"设置 → AI"里加一个` |
| `SettingsView.swift:211` | `自动处理低风险问题` | `自动修复不用动系统设置的小问题` |
| `SettingsView.swift:303` | `AI 供应商` | `AI 服务` |
| `SettingsView.swift:322` | `脱敏级别：均衡/严格` | `隐私保护：默认/严格` |
| `SettingsView.swift:327` | `上传确认：每次询问/始终允许/永不上传` | `发报告前：每次问我/总是发送/从不发送` |
| `SettingsView.swift:333` | `允许带截图问 AI` | `可以发送截图给 AI` |
| `SettingsView.swift:340` | `模型` + `Base URL` | 折叠到"高级"，首页别出现 |
| `SettingsView.swift:360` | `跨重启保留本地预算计数` | 折叠到"高级"，改名 `记住我的使用次数` |
| `SettingsView.swift:745-748` | `保留最近诊断报告` + `自动裁剪事件日志` + `保存完整代理身份报告` | 合并成 `数据保留` 一个开关 |

---

## 7. 是否值得继续做

**这个产品方向是否成立**：成立。普通用户买代理不会用是真实痛点，市场上有 V2RayN、Clash、Shadowrocket 都是工程师工具，留下的"非工程师"用户是真实人群。

**如果成立，最短几步能变成用户愿意用的版本**：
1. 删 `iphone-v2rayn-package-2026-06-14/`（P0-1，1 小时）
2. onboarding 改标题 + 副标题（P0-5，2 小时）
3. 代理部署单页化 + 中文 confirm 弹窗，删 `APPLY_PROXY_PROFILE` 短语（P0-3 / P0-4，4 小时）
4. 状态卡加 `displayName`，翻译 6 个核心 ID（P0-6，4 小时）
5. 错误 banner 加"一键修复"按钮调 `primary_action`（P1-2，4 小时）
6. SettingsView 砍服务 Tab、折叠高级设置（P1-1，2 小时）
7. 写 5 个 e2e acceptance case（P1-4，1 天）
8. Keychain 加 ACL + 网关换 IPv6 防护（P1-6 / P1-7，1 天）

**总：约 4 个工作日。**

**如果不成立，为什么**：这个产品**当前**不成立。P0-1/P0-2 的工作区脏数据 + P0-3 的英文确认短语 + P0-5 的"AI 开发工具"标题，让"产品对普通用户成立"这个命题在用户第一次打开时就被证伪。

**现在距离"可以发给真实普通用户试用"还差什么**：
- **必须解决**：P0-1/P0-2/P0-3/P0-4/P0-5/P0-6
- **强烈建议**：P1-1/P1-2/P1-3（错误体验 + 术语翻译）
- **不能省**：至少 5 个 e2e acceptance case 跑通

---

## 8. 30 天落地路线图

### 第 1 周 — 修 6 个 P0 + 改 onboarding 文案
- 修：P0-1（删旧资料包）、P0-2（DMG/zip ignore）、P0-3（删英文短语）、P0-4（单页化部署）、P0-5（onboarding 改标题）、P0-6（displayName）
- 验收：
  - `release_audit.py --json` 退出码 0
  - `git status` 干净，无 DMG/zip stage
  - 用户点"部署" → 中文 confirm → 部署，无英文短语
  - 状态卡显示人话，5 个朋友都看得懂

### 第 2 周 — 错误体验 + Settings 降噪 + AI 联动
- 修：P1-1（Settings 砍 Tab 折叠高级）、P1-2（错误 banner 一键修复）、P1-3（AI 弹窗上下文）
- 验收：
  - Settings 3 Tab，新用户 30 秒找到"换 API Key"
  - 错误 banner 每个配 1 个明确修复按钮
  - AI 弹窗根据代理/诊断上下文预填 3 条快捷提示

### 第 3 周 — 验证 5 个 e2e acceptance + 测试重构
- 修：P1-4（5 个 e2e）+ 把现有 360 个 pytest 拆"后端逻辑 / UI 字符串 / e2e"三层
- 验收：
  - e2e fixture 跑通：粘贴→预检→部署→恢复→回滚
  - CI 加 `verify_dmg_backend.sh` 必跑
  - `pytest --tb=no -q` 仍 360+5 = 365 passed

### 第 4 周 — 工程加固 + 发布卫生
- 修：P1-5（API token rotation）、P1-6（Keychain ACL）、P1-7（IPv6 真实防护）、`release_export.py` 改输出到 `dist/`
- 验收：
  - `security find-generic-password` 在没 Netfix bundle 时返回空
  - 部署后 IPv6 评估返回 `"status": "checked"`
  - `git status` 永不出现 DMG/zip
  - `release_readiness.py` 退出码 0

### 每周的验收标准

| 周 | 核心验收 |
|---|---|
| 1 | release_audit 退出码 0 + onboarding 5 秒看懂 + 部署无英文 |
| 2 | Settings 30 秒找到 API Key + 错误配修复 + AI 上下文联动 |
| 3 | 5 个 e2e case 全过 + CI 跑 verify_dmg_backend |
| 4 | Keychain ACL + IPv6 真实防护 + git 干净 + release_ready |

---

## 附录 A：已确认修掉但仍需用户验证的事项

- **`APPLY_PROXY_PROFILE` 短语已由 SettingsView 验证通过**（`tests/test_macos_proxy_export_ui.py:106-139` 期望 SettingsView 出现"让这台 Mac 用代理上网"/"粘贴整行参数"/"我去哪里复制？"/"部署到这台 Mac"），但**ProxySetupView 还没回灌这些新文案**（`ProxySetupView.swift:88-92` 仍是"保存到这台 Mac"）。
- **Status bar / NSAlert 三按钮已实现**（`AppDelegate.swift:149-169` "恢复网络设置后退出"/"取消退出"/"仍然退出"），但 `tests/test_macos_quit_bridge_guard.py:11-31` 只测字符串字面量存在，无 e2e 验证按钮按下后真实回滚。
- **Keychain 写入走 stdin**（`scripts/release_audit.py` 接受，"Keychain writes now pass secrets to the macOS `security` CLI via stdin with `-w` as the last option" `RELEASE_CANDIDATE_SPRINT_2026_06_24.md:176-177`），但 ACL 限制**没加**（P1-6）。

## 附录 B：实际跑过的命令及结果

```text
python3 -m pytest -q
→ 360 passed in 85.87s (0:01:25)

python3 scripts/release_audit.py --json
→ ok: false, 13 blocker findings (全部命中 iphone-v2rayn-package-2026-06-14/)

cd gui/macos && swift build -c release
→ Build complete! (0.16s)

NETFIX_REQUIRE_BUNDLED_RUNTIME=true ./scripts/verify_dmg_backend.sh Netfix-0.2.0.dmg
→ DMG backend verification passed
   bundled_backend: true, bundled_python: false
   run_services_ai: "网络看起来正常" (16 diagnostics)
   llm_chain_readiness: ["image_question", "text"]
   proxy_bridge_auto_restart_default: false
   proxy_import_preview: 1 valid / 1 skipped / 1 ready
   disable_ipv6_dry_run: "dry-run"
   proxy_profile_replace: ok (socks5h)
   proxy_client_package: "mihomo"
   bridge_lifecycle: "stopped", startup_checked: true

rg -n "Tier|root cause|DNS 层|出口身份|user123|pass456|..." gui/macos/Sources docs tests/test_macos_*
→ 主要命中文档（PROXY_DEPLOY_AUDIT / PRODUCT_AUDIT）而非 UI 字符串
→ UI 中残留: DashboardView.swift:10 "autoFixTier1" (字段名) + DashboardView.swift:743 "自动修复" (UI 文案已脱敏)
→ SettingsView.swift:12 "autoFixTier1" + SettingsView.swift:211 "自动处理低风险问题" (UI 脱敏)
→ HealthMonitor.swift:121 "netfix.autoFixTier1" + :127 "hasTier1" (内部判断，已脱敏)
```

---

> **审计结束语**：后端 80% 覆盖，UI 15% 覆盖，e2e 0% 覆盖。普通用户路径在 12 步中有 3 处明确断点（P0-3、P0-4、P0-5）。`iphone-v2rayn-package-2026-06-14/` 旧资料包是发布卫生灾难，必须先清。30 天内能变成"勉强能试用"版本，60 天内能变成"普通用户愿意用"版本。
