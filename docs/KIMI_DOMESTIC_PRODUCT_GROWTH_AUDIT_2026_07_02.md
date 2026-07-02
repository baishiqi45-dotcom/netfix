# Netfix 国内产品冷审与增长路线图

> 审计视角：国内真实用户、中文开源传播、macOS 小白用户、AI Agent 用户、代理/网络故障场景
> 审计日期：2026-07-02
> 审计人：Kimi Code CLI

---

## 0. 一句话结论

Netfix 的工程骨架已经成形，但它现在同时穿着三件外套：代理客户端、AI 工具修网器、网络诊断 CLI。国内最大的人群——**买了代理不会配 Mac 的普通用户**——在 GitHub 首页 5 秒内看不明白自己是目标用户。产品必须先做减法：首屏只讲「粘贴一行让 Mac 安全上网」，把 MCP、CLI、AI 解释全部折叠到二级。App 的代理配置流程要从「工程师调试面板」改成「四步向导」，错误提示要从技术码翻译成「账号错了/节点挂了/网络问题/App 问题」。完成这些，Netfix 才值得被 Star 和传播。

---

## 一、国内用户视角重新定义产品

### 1. 国内用户第一眼会以为这是干嘛的？

看 README 首屏 5 秒，国内用户通常产生三种互相打架的印象：

1. **「又一个代理/机场客户端」**——看到「代理参数」「Clash / sing-box / mihomo」会往 ClashX、v2rayU 归类。
2. **「给程序员修 AI 工具的」**——看到 `Codex / ChatGPT / GitHub`、`MCP ready` 会以为是 Cursor/Codex 插件。
3. **「Mac 网络急救工具」**——看到「网络急诊」「DNS、系统代理、IPv6、TLS」会以为是系统网络修复软件。

问题：三种身份混在一起，小白不知道自己是目标用户还是路过用户。

### 2. 国内用户最真实的痛点

| # | 真实痛点（用户原话化） | README/文档对应 | 是否说清楚 |
|---|------------------------|-----------------|------------|
| 1 | 买了代理，Mac 上不知道往哪填 | README 第 14 行：「已有合法代理参数但不会配置 Mac」 | ⚠️ 基本清楚，但「合法代理参数」像法律声明 |
| 2 | ChatGPT / GitHub / Codex 突然打不开 | README 第 16 行：「macOS 上 Codex / ChatGPT / GitHub 突然连不上」 | ⚠️ 清楚，但把小白挡在外面 |
| 3 | 怕把电脑网络改坏，改完回不来 | README 第 18 行：「点确认才改网络，改完可以一键回滚」 | ⚠️ 有提到，首屏不够醒目 |
| 4 | 怕代理密码、API Key 被偷走 | README 第 19、132 行：「密码进入 macOS Keychain」 | ⚠️ 有，但「脱敏」「Keychain」术语小白不懂 |
| 5 | 不想开终端，只想双击 App 搞定 | README 第 22 行给了 `curl \| bash`，第 92 行说目标形态是 App | ❌ 首屏两个命令，App 不够突出 |
| 6 | 双击安装弹「无法验证开发者」，不敢点 | README 第 24 行小字提醒 | ❌ 警告级别不够，没有图文引导 |
| 7 | 不知道服务商后台该复制哪一行 | README 第 106-119 行给了格式示例 | ⚠️ 列了格式，没说不要复制订阅链接 |

**没说清楚的痛点**：
- 保存和部署为什么要分两步（App 里的 P0 问题，README 没预警）。
- 安装脚本 `curl | bash` 到底改了哪些文件、怎么卸载。
- 不接 API Key 是不是「残血版」。

### 3. Netfix 最应该打哪个痛点？

**最应该打：「买了代理不会配 Mac」**。

理由：
1. 人群最大：会用 ChatGPT/Codex 的人只是开发者子集；买了代理不会配的运营、设计、学生、自由职业者大得多。
2. 痛点最直接：「粘贴一行就能上网」5 秒能说清因果。
3. 竞争空白：Clash/V2RayN 都是工程师工具，非工程师 Mac 用户没人管。
4. AI 急救应作为第二卖点：用户已经用上代理后，再告诉他「Codex 断线也能修」，顺理成章。

### 4. 现有中文一句话定位的问题

现有：「已有合法代理参数但不会配置 Mac？Netfix 让你粘贴一整行连接信息，先检查能不能用，再保存到本机，最后由你确认是否让这台 Mac 开始使用。」

问题：
- 开篇就是「合法代理参数」，像法律声明。
- 没说结果——「让 Mac 上网」这种大白话没有出现。
- 一句话塞了「检查、保存、确认」三个动作，像操作手册。
- hero 图 alt「本地网络急诊工具」太像医院挂号。

### 5. 建议的中文定位、Slogan、README 首屏结构

**中文定位**：
> **买了代理不会配？粘贴一行，让 Mac 安全上网。**

副标题：
> Netfix 会检测你的代理能不能用，再帮你部署到这台 Mac。改之前自动备份，随时一键回滚。

**Slogan 候选**：
- 主 Slogan：**粘贴即上网，改坏能回滚**
- 次 Slogan：**让 Mac 连上你的代理，不用懂网络**
- 信任 Slogan：**密码只进 Keychain，不上传**

**README 首屏前 5 屏结构**：

1. **标题 + 信任 + 主 CTA**
   ```
   # Netfix
   > 买了代理不会配？粘贴一行，让 Mac 安全上网。
   🔒 密码只存 Keychain  🏠 默认离线诊断  🛡️ 改前备份 / 一键回滚  🙅 不卖代理
   [一键安装 macOS App]    [从源码运行]
   ```

2. **QA 版安装警告**
   > ⚠️ 当前是 v0.2.0-qa.1 预览版，DMG 尚未完成 Apple 签名与公证。首次打开请在「系统设置 → 隐私与安全性」点击「仍要打开」。附图文步骤。

3. **三步流程（配 GIF）**
   - 粘贴服务商给的那行连接信息
   - Netfix 自动检测地址、端口、密码对不对
   - 点「开始用这台 Mac 上网」，先备份再应用

4. **真实 case / 对比表**
   - 一句话引用 `cases/2026-06-29-普通用户代理部署体验审查.md`
   - 对比表：Netfix vs 手动配系统代理 vs ClashX

5. **隐私安全 + FAQ**
   - 密码/API Key 只存 Keychain
   - 不接 API Key 也能用
   - 改坏网络能回滚
   - 不卖代理、不内置节点

### 6. README 首屏应该先讲「代理部署」还是「AI 工具断线急救」？

**明确结论：先讲「代理部署」**。

理由：会买代理不会配 Mac 的人远多于会写代码且用 Codex 的人；用户先要让 Mac 能上网，然后才会关心 Codex 断线怎么办；「粘贴一行让 Mac 上网」比「AI 开发工具断线急救」更容易传播。

AI 工具断线急救应作为第 2 卖点，放在「它还能做什么」或「真实案例」里。

---

## 二、普通小白用户冷审

扮演一个不会命令行、不会看 JSON、不会配置系统代理的 Mac 用户，从 GitHub 首页到真正上网，完整卡点如下。

### GitHub 首页阶段

| # | 卡点描述 | 所在文件/界面 | 用户会怎么误解 | 应该改成什么 | 优先级 |
|---|---------|--------------|--------------|-----------|--------|
| 1 | hero 图 alt 写「macOS 本地网络急诊工具」 | README.md 第 5 行 | 以为是医院挂号系统或系统急救软件 | 「粘贴代理，让 Mac 上网」 | P0 |
| 2 | 首屏 badges 有 `MCP ready` | README.md 原第 10 行 | 不认识 MCP，以为是高科技门槛 | 移到开发者小节 | P0 |
| 3 | 首屏 badges 有 `privacy: local-first` | README.md 原第 9 行 | 不懂 local-first 什么意思 | 「隐私：本地优先」或「离线可用」 | P1 |
| 4 | 第一句话是「已有合法代理参数」 | README.md 原第 14 行 | 像法律声明，紧张 | 「你已有代理账号」 | P0 |
| 5 | 首屏同时出现两个 `curl \| bash` | README.md 原第 23-29 行 | 不知道该装 App 还是装 MCP | 只留 App 安装，MCP 折叠 | P0 |
| 6 | 「Codex / ChatGPT / GitHub」出现在第一句附近 | README.md 原第 16 行 | 非开发者觉得自己不是目标用户 | 放到第二屏「还能做什么」 | P0 |
| 7 | 首屏堆砌 DNS / 系统代理 / IPv6 / TLS / 代理核心 | README.md 原第 17 行 | 信息过载，像上课 | 折叠到技术详情 | P0 |
| 8 | 没有 Gatekeeper 「仍要打开」图文引导 | README.md 原第 24 行仅一行小字 | 弹窗时不敢点，直接卸载 | 加醒目 warning block + 截图步骤 | P0 |
| 9 | QA 版未签名提示不够警告级别 | README.md 原第 55、65-71 行 | 用户当作正式版传播 | 安装命令上方加 ⚠️ 色块 | P0 |
| 10 | 「代理到底复制什么」标题像让复制代理本身 | README.md 原第 106 行 | 去复制出口 IP | 「你该从服务商后台复制什么」 | P1 |
| 11 | 代理格式示例放在 FAQ 之后才展开 | README.md 原第 110-118 行 | 用户粘贴错误格式后才知道不支持 | 输入框下方直接列 ✅ ❌ 格式 | P0 |
| 12 | 没说「不支持 ss:// / vmess:// / Clash 订阅链接」到首屏 | README.md 原第 135 行 | 小白直接粘贴 Clash 订阅，报错放弃 | 在粘贴引导处直接说明 | P0 |
| 13 | 安装脚本默认拉 `main` 分支 | README.md 原第 57-65 行 | 明天代码变了怎么办 | 默认 pin release tag | P1 |
| 14 | `SECURITY.md`、`CONTRIBUTING.md` 全英文 | 根目录 | 国内用户和贡献者直接跳过 | 提供中文版或中英双语 | P1 |
| 15 | 没有卸载/回滚命令的快速入口 | README.md 原第 181 行 `rollback` 只在 AGENTS.md | 装完后悔了找不到路 | README 加「后悔了怎么办」小节 | P2 |
| 16 | 真实案例只列文件名，没有一句话摘要 | README.md 原第 99-103 行 | 懒得点进去 | 每 case 给一句人话摘要 | P1 |

### App 安装阶段

| # | 卡点描述 | 所在文件/命令 | 用户会怎么误解 | 应该改成什么 | 优先级 |
|---|---------|--------------|--------------|-----------|--------|
| 17 | 默认推荐 `curl ... \| bash` 一键安装，无法直接 `--dry-run` | README.md + 三个脚本 | “这命令会不会黑进我电脑？” | 给出 `bash -s -- --dry-run` 示例和“先下载再检查”方式 | P0 |
| 18 | App 装到 `~/Applications`，用户去 `/Applications` 找不到 | `install_mac_app_from_github.sh` 第 17 行 | “终端说装好了，为什么应用程序文件夹里没有？” | 安装后 `open -R` 高亮；或明确提示路径 | P0 |
| 19 | Gatekeeper 拦截没有自动处理，也没有清晰引导 | `install_mac_app_from_github.sh` 第 193-198 行 | “弹窗说我无法打开，我是不是下载到病毒了？” | 提前 `xattr` 或清晰打印系统设置路径 | P0 |
| 20 | 没有给出卸载命令，用户不会发现 `--uninstall` | `install_mac_app_from_github.sh` 第 22-23 行 | “我想删掉这个 App，怎么没有卸载按钮？” | README 和脚本结尾都打印卸载命令 | P0 |
| 21 | Codex MCP 安装默认拉 `main` 分支，版本不固定 | `install_codex_mcp_from_github.sh` 第 7-8、13 行 | “今天装的和昨天装的怎么文件不一样？” | 默认锁定最新 release tag | P1 |
| 22 | 源码包没有 SHA256 校验 | `install_codex_mcp_from_github.sh` 第 120-122 行 | “下载被中间人改了怎么办？” | 发布时附带 checksums.txt | P1 |
| 23 | Kimi/Claude/Cursor 用户没有自动配置路径 | `install_mcp.sh` 第 88-98 行；README.md | “我也是 AI 工具用户，凭什么只有 Codex 能一键装？” | 生成配置片段并说明粘贴位置 | P1 |
| 24 | `install_mcp.sh` 打印的 Kimi 配置到 stderr，小白看不到 | `install_mcp.sh` 第 91-94 行 | “终端跑完啥也没有，Kimi 怎么配？” | 输出到 stdout，并附带“复制下面内容到 …”说明 | P1 |
| 25 | 安装成功后的提示信息里没有“下一步” | 三个脚本结尾 | “装完了，然后呢？” | 结尾打印 App 位置、验证命令、卸载方法 | P0 |

### App 内代理配置阶段

| # | 卡点描述 | 所在界面/文件 | 用户会怎么误解 | 应该改成什么 | 优先级 |
|---|---|---|---|---|---|
| 26 | App 名称全小写 `netfix`，Dock/菜单栏缺乏品牌识别 | `NetfixApp.swift`、`AppDelegate.swift` | 以为自己开错了 App | 统一使用 `Netfix` 作为显示名 | P1 |
| 27 | 首次启动没有真正引导用户去系统设置授权本地网络 | `OnboardingView.swift` | 点“我已授权，继续”后发现权限根本没开 | 点按钮后自动打开系统设置并显示阻塞提示 | P0 |
| 28 | “本地网络权限”这个术语对小白太抽象 | `OnboardingView.swift` | 不知道这个权限和“能不能上网”有什么关系 | 改成“允许 Netfix 查看你的 Wi-Fi 和路由器状态” | P1 |
| 29 | ProxySetupView 出现“基线检测”“代理客户端”等技术词 | `ProxySetupView.swift` | 以为必须先运行基线检测才能继续 | onboarding 只做一件事：引导粘贴代理或跳过 | P0 |
| 30 | 两个检查按钮“检查这行能不能用”和“保存并测试”同时出现，顺序不明 | `ProxySetupView.swift` | 不知道该先点哪个 | 改为线性流程：粘贴 → 检查 → 保存 → 部署 | P0 |
| 31 | “保存并测试（暂不改网络）”文案没有解释“测试”测的是什么 | `ProxySetupView.swift` | 以为点了之后就能上网了 | 改成“保存到我的 Mac（暂不影响浏览器）” | P0 |
| 32 | “开始使用这台 Mac 上网”按钮在保存成功后才出现，没有引导 | `ProxySetupView.swift` | 保存成功后不知道还要再点一次 | 保存成功后自动高亮部署按钮 | P0 |
| 33 | 部署确认框没有说明“所有 App 都会走代理” | `ProxySetupView.swift`、`SettingsView.swift` | 以为只影响浏览器，结果微信/网银也走代理 | 确认框明确列出影响范围，提供“仅浏览器使用”选项 | P0 |
| 34 | 四段式代理 `host:port:user:pass` 默认按 HTTP 处理 | `ProxySetupView.swift` | 明明是 SOCKS5 节点，粘贴后却当 HTTP 用 | 增加协议自动探测或强制用户确认协议 | P1 |
| 35 | 没有告诉用户“代理参数从哪里复制” | `ProxySetupView.swift` | 随便复制一个 IP 或订阅链接就粘贴 | 增加“去服务商后台复制”图文步骤 | P0 |
| 36 | Dashboard 状态卡片只显示前 3 项，失败时看不到关键信息 | `DashboardView.swift` | 看到“网络连接 异常”但不知道哪一项异常 | 失败卡片默认展开显示失败项 | P0 |
| 37 | Dashboard 主界面没有“当前是否使用 Netfix 代理”的明确指示 | `DashboardView.swift` | 不知道自己现在是不是在走代理 | 顶部状态条增加“未使用代理 / 正在使用 XX 代理” | P0 |
| 38 | “一键诊断”耗时最长 120 秒，进度条只是假进度 | `DashboardView.swift` | 卡在 90% 很久，以为 App 死了 | 显示真实步骤和预计时间 | P1 |
| 39 | 错误横幅只做了 3 种人话映射，其他错误直接露技术文案 | `DashboardView.swift` | 看到“HTTP 错误 500：fix_command_failed”直接放弃 | 建立完整的错误码到人话映射表 | P0 |
| 40 | 诊断结果不区分“账号密码错 / 服务商挂了 / 网络问题 / App 问题” | `DashboardView.swift`、后端 `explanation` | 不知道该换密码、换节点还是重启 App | 结果卡片顶部增加“问题类型”标签 | P0 |
| 41 | “恢复原来的网络设置”按钮永远可用 | `DashboardView.swift` | 没部署过代理也点 | 根据代理状态动态显示 | P1 |
| 42 | AI 解释需要手动打开、勾选同意、发送，步骤太多 | `DashboardView.swift` | 看到复杂弹窗直接关闭 | 诊断失败时自动提供“用一句话解释”按钮 | P1 |
| 43 | 设置页“Agent”标签名不直观 | `SettingsView.swift` | 不知道 Agent 是什么 | 改名为“AI 编程助手” | P1 |
| 44 | AI 设置页高级选项默认折叠但仍显示大量字段，信息过载 | `SettingsView.swift` | 小白被 Base URL、模型、密钥名称吓到 | 提供“简单模式”：只显示开关、供应商、Key、测试 | P0 |
| 45 | 没有“从剪贴板一键粘贴 API Key”的快捷入口 | `SettingsView.swift` | 要手动切回 App、找到输入框、粘贴 | 增加“粘贴剪贴板中的 Key”按钮 | P1 |
| 46 | “导入 DeepSeek 侧车 Key”按钮术语晦涩 | `SettingsView.swift` | 完全不理解“侧车”是什么意思 | 改名为“自动读取 DeepSeek 配置”或隐藏到高级模式 | P1 |

---

## 三、国内开源传播与 Star 增长审计

### 1. 传播平台画像

| 平台 | 适合传播什么 | 用户期待 |
|------|-------------|---------|
| **V2EX** | 开发者工具首发、冷启动 | 技术细节、真诚、接受质疑 |
| **少数派** | Mac 应用推荐、效率工作流 | 高颜值截图、使用场景、作者故事 |
| **B站** | 工具演示、教程 | 录屏实操、前后对比、口语化 |
| **即刻** | Build in Public、短更新 | 创始人日常、版本迭代、真实数据 |
| **知乎** | 技术选型、深度测评 | 结构化分析、可复现步骤 |
| **掘金** | 技术文章、源码解析 | 代码片段、踩坑记录 |
| **小红书** | 效率工具、AI 工具种草 | 真实体验、短文案、首图精美 |
| **Telegram/微信群** | 种子用户、beta 测试 | 快速支持、私密感 |

### 2. 10 个最容易传播的中文标题

1. Mac 用户进！一键诊断 AI 工具连不上，告别反复 ping
2. 开源免费｜我把网络排查做成了 3 秒出结果的 Mac 菜单栏工具
3. Cursor/Claude 提示 network error？这个命令行医生能定位到哪一层挂了
4. 网又抽风？这个国产开源工具比系统自带监控更懂网络
5. 当 AI Agent 报连接失败，我写了这个本地诊断器
6. 小红书首发｜Mac 网络问题不用猜，一行命令看全链路
7. 不再盲调系统代理：一个工具自动检测 Codex/ChatGPT 可达性
8. 开发者必备：把 DNS、代理、Wi-Fi 体检装进一个 CLI
9. 从“怎么又连不上”到“找到根因了”：Netfix 使用实录
10. Mac 网络诊断神器开源了｜自动给 AI 工具做连通性体检

### 3. 10 个 README 首屏卖点文案

1. 一条命令，自动检查 Mac 当前代理、Wi-Fi、DNS 和 AI 服务可达性。
2. 把散在 `scutil`/`networksetup`/`ping` 里的网络信息，聚合成一份 JSON 体检报告。
3. AI Coding 工具连不上？`netfix.py codex` 直接告诉你问题在哪一层。
4. 本地规则引擎 + 多探针诊断，先定位根因，再决定要不要改配置。
5. Tier 1 自动修复 DNS 缓存、刷新代理状态；Tier 2/3 只给明确步骤，绝不瞎改。
6. 支持 HTTP API 与 MCP Server，让 AI Agent 自己调用网络诊断能力。
7. 纯本地运行，不上传任何数据，Mac 网络问题的隐私安全首选。
8. 一行命令回滚上一次配置变更，改坏了也能一键还原。
9. 内置知识库 `kb`，把常见症状和修复方案沉淀成可搜索的 runbook。
10. 开源免费，Homebrew 一键安装，GitHub CI 保证每次发布可回滚。

### 4. 10 个短视频/GIF 演示选题

1. 3 秒体检：`python3 netfix.py codex --json` 到输出完整报告。
2. 痛点对比：手动输入 5 个命令 vs Netfix 一键输出。
3. AI 工具连不上：运行 codex 子命令，看 diagnostics 哪一步失败。
4. 从终端到 GUI：实时网络状态的可视化切换。
5. DNS 缓存修复前后：网页打不开 → flush-dns → 刷新恢复。
6. 代理状态可视化：当前系统代理、运行中的核心、活动节点。
7. 回滚操作：不小心改错配置，`netfix.py rollback` 一键还原。
8. MCP 集成：在 Cursor/Kimi 里调用 netfix 工具诊断网络。
9. 知识库查询：`netfix.py kb --query MTU` 给出修复步骤。
10. 多平台安装：Homebrew install + 首次运行向导。

### 5. 10 个真实 case 选题

1. Cursor 提示 model provider doesn’t serve your region，代理开着，Netfix 定位到 HTTP/2 协商失败。
2. Claude Code 每 15 分钟断一次，Netfix 发现是公司 VPN 路由冲突。
3. ChatGPT API 返回 timeout，Netfix 显示 DNS 解析到不可达节点。
4. Wi-Fi 能刷国内站点但打不开 GitHub，Netfix 诊断出系统代理未生效。
5. 新装 sing-box/mihomo 后 AI 工具反而连不上，Netfix 识别端口冲突。
6. 公司内网堡垒机下 Copilot 掉线，Netfix 给出分流规则建议。
7. Mac 升级后菜单栏代理图标消失，Netfix 检测代理核心仍在运行。
8. AI Agent 调用本地 MCP server 失败，Netfix 发现是 IPv6 优先级问题。
9. 家用路由器 DNS 污染导致 OpenAI API 间歇性失败，Netfix 建议切换 DNS。
10. 开发机 ping 通但 curl 不通，Netfix 追踪到 SSL/TLS 证书链异常。

### 6. 10 个 GitHub issue/example 模板方向

1. Bug report：必须附带 `netfix.py doctor --json` 输出。
2. Feature request：新增某种 AI 服务或代理核心的诊断探针。
3. Case study：提交 `cases/YYYY-MM-DD-关键词.md` 真实症状记录。
4. README 素材：上传/替换首屏 screenshot 或 demo GIF。
5. i18n 贡献：翻译 README 或 CLI 输出到新的语言。
6. 规则贡献：向 `rules/services.json` 或 `rules/symptoms.json` 添加条目。
7. 平台兼容性：Apple Silicon / Intel / 不同 macOS 版本的专项问题。
8. 企业/VPN 环境：公司内网、堡垒机、SD-WAN 下的诊断问题。
9. 性能回归：CLI 冷启动、JSON 输出耗时、老机型卡顿。
10. Good first issue：优化错误提示文案或增加 `--dry-run` 示例。

### 7. 合规表达注意事项

- 统一使用「网络诊断」「连通性检测」「本地配置管理」「AI 工具可达性」等中性词。
- 不主动讨论翻墙、代理节点推广、违反平台规则、账号批量操作等高风险内容。
- README 已明确：不卖代理、不内置节点、不承诺第三方服务质量、不做规避。

---

## 四、国内竞品/参考项目研究

### 代理/网络客户端

**1. Clash Verge Rev**
- 入口：GitHub Release + 包管理器 + 官网。
- 解决：Clash 停更后的跨平台图形化继任者。
- 值得学：多平台安装渠道清楚，Mac 分 Intel/Apple Silicon。
- 容易卡：WebView2 / 系统扩展授权；小白分不清「系统代理」和「TUN 模式」。
- Netfix 避坑：不要把所有模式堆在首屏，默认只给「系统代理」一个开关。
- Netfix 差异化：不做「又一个 Clash GUI」，而是做「Clash 后面的网络医生」。

**2. ClashX / ClashX Pro**
- 入口：DMG 拖拽安装 + 菜单栏猫咪图标。
- 解决：macOS 最经典的 Clash 客户端。
- 值得学：菜单栏交互极简；首次启动 Helper 明确告诉用户为什么需要密码。
- 容易卡：原仓库已下架，小白容易下到带毒山寨版；关闭后系统代理残留。
- Netfix 避坑：官方分发渠道要唯一、可验证；退出时必须自动清理系统代理。
- Netfix 差异化：检测系统里残留的 ClashX 代理设置并一键修复。

**3. Mihomo Party（Clash Party）**
- 入口：GitHub Release，macOS 首次打开要 `xattr` 命令。
- 解决：基于 mihomo 的跨平台客户端。
- 值得学：导入订阅后自动测速并推荐最快节点；FAQ 直接列出「应用已损坏」命令。
- 容易卡：Windows 非管理员运行直接报错；macOS 签名问题要自己跑命令。
- Netfix 避坑：给 Mac 包做公证，避免用户去搜 quarantine 命令。
- Netfix 差异化：把「节点推荐」做成诊断——告诉用户「这个节点为什么现在慢」。

**4. sing-box / SFI / SFM**
- 入口：GitHub Release、Homebrew Cask、App Store（非大陆 ID）。
- 解决：新一代通用代理平台。
- 值得学：macOS standalone 版可用 Homebrew 一键装；Remote/Local 配置分得清楚。
- 容易卡：App Store 需要外区账号；SFM 首次要安装 Network Extension；JSON 报错对小白不友好。
- Netfix 避坑：不要把 iOS/macOS 上架当成主要入口，官网直签 + Homebrew 更稳。
- Netfix 差异化：做 sing-box 的「配置翻译器」和「连接前体检」。

**5. v2rayN / v2rayU**
- 入口：GitHub Release，v2rayN 有「带 core」完整包。
- 解决：Windows 最主流的 V2Ray/Xray 客户端。
- 值得学：导出分享链接/二维码，方便手机同步；路由规则「绕过大陆」预设。
- 容易卡：v2rayN 依赖 .NET 运行时；v2rayU 没有 Apple 签名。
- Netfix 避坑：安装包要自带运行时或提示下载；macOS 必须签名。
- Netfix 差异化：做「协议自动降级」——检测当前网络下哪个协议能通。

**6. Shadowrocket**
- 入口：非大陆区 App Store，$2.99 一次性买断。
- 解决：iOS 最成熟的规则代理客户端。
- 值得学：价格极低、口碑传播极强；支持扫码和订阅导入。
- 容易卡：门槛是「怎么买到外区 Apple ID 和礼品卡」。
- Netfix 避坑：如果做 iOS 版，必须解决国内用户如何安装的第一公里问题。
- Netfix 差异化：iOS 侧「一键诊断」——检测 VPN 配置、DNS、证书状态。

**7. Surge**
- 入口：Mac/iOS/Apple TV App Store，免费下载 + 内购订阅。
- 解决：高端网络调试 + 代理一体化工具。
- 值得学：首次启动给示例配置；Dashboard 看实时请求；sub-store 订阅转换生态。
- 容易卡：价格贵、学习曲线陡；配置文件语法自己写。
- Netfix 避坑：不要学 Surge 把全部高级功能都暴露给小白；定价要分层。
- Netfix 差异化：把 Surge 的「请求可视化」搬到诊断里，但不需要写规则。

**8. Quantumult X**
- 入口：非大陆区 App Store。
- 解决：iOS 功能最全的代理+重写+脚本+MitM 工具。
- 值得学：支持「懒人配置」一键导入；资源解析器自动转换 Clash 订阅。
- 容易卡：配置文件分段多；MITM 证书安装步骤长。
- Netfix 避坑：不要让用户直接面对分段配置文件；证书安装向导要一步一确认。
- Netfix 差异化：做「配置健康检查」——自动检测哪些远程规则失效、哪些证书过期。

**9. Hiddify**
- 入口：官网下载页，支持多平台。
- 解决：基于 sing-box 的多协议客户端，强调新手友好。
- 值得学：首次启动引导选地区；连接按钮极简，自动测速选节点；支持多种订阅格式。
- 容易卡：Windows 可能缺 VC++ 运行库；macOS 未签名要「仍要打开」。
- Netfix 避坑：Windows 安装包要预装或检测 VC++；macOS 签名和公证必须做。
- Netfix 差异化：Hiddify 做「连接」，Netfix 做「连接前的体检」。

### 开发/调试代理工具

**10. Proxyman / Charles / mitmproxy**
- 入口：官网 / pip / brew。
- 解决：HTTPS 抓包、API 调试。
- 值得学：Proxyman 原生 Swift、遵循 macOS HIG。
- 容易卡：证书安装和信任是最大门槛。
- Netfix 避坑：如果涉及抓包诊断，证书安装向导必须自动化。
- Netfix 差异化：把 Proxyman 的「流量可视」和 mitmproxy 的「脚本化」结合成 AI 可读的 JSON 诊断报告。

### 异地组网/内网穿透

**11. Tailscale / ZeroTier / NetBird**
- 入口：官网下载 + Google/GitHub 账号登录。
- 解决：无公网 IP 的异地组网。
- 值得学：Tailscale MagicDNS、Exit Node 概念直观；NetBird 全开源且带 Web 后台。
- 容易卡：官方服务器在国外，国内下载慢、登录靠 Google/GitHub；NetBird 自建门槛高。
- Netfix 避坑：国内用户不要假设他们能直连 GitHub/Google 登录；提供国内镜像下载。
- Netfix 差异化：专注做「最后一公里诊断」——为什么 Tailscale 打洞失败、为什么 NetBird 走 Relay。

### AI 工具的网络配置痛点

**12. OpenCat / ChatWise / Cherry Studio / Cursor / Claude Code / Kimi Code**
- 入口：各官网下载桌面客户端或 npm 安装 CLI。
- 解决：聚合多个大模型、统一对话/编程界面。
- 值得学：Cherry Studio 把代理模式做成下拉框；ChatWise/Cherry Studio MCP 配置入口清晰。
- 容易卡：Cursor/Claude Code 国内经常断；API Key 体系混乱；环境变量配置容易写错；MCP 安装要配 uv/bun/npx。
- Netfix 避坑：不要让用户手动改 `~/.zshrc` 里的 base_url；MCP server 安装要自动检测依赖。
- Netfix 差异化：做「AI 工具网络适配层」——自动检测各工具需要访问的域名，生成最小化分流规则。

### MCP 相关开源工具

**13. modelcontextprotocol/servers**
- 入口：`npx -y @modelcontextprotocol/server-xxx`。
- 解决：给 AI Agent 提供标准文件/网络/数据库/仓库访问能力。
- 值得学：一行命令即可启动，配置片段直接可复制到 Claude Desktop。
- 容易卡：需要 Node/Python 环境；路径授权容易写错。
- Netfix 避坑：默认路径授权最小化，给出沙箱提示。
- Netfix 差异化：把自身诊断能力封装成 MCP tool。

**14. FastMCP / Playwright MCP / ChatMcp / Claude Code Router**
- FastMCP 降低写 Server 的心智负担；Playwright MCP 让 AI 操控浏览器；ChatMcp 统一测试管理多个 MCP Server；Claude Code Router 把 Anthropic 请求转发到国内 cheaper 模型。
- Netfix 可以借鉴：FastMCP 的极简装饰器、Playwright 的「真实访问验证」、Router 的「模型切换中间层」概念。
- Netfix 差异化：诊断结果作为 ChatMcp 数据源 MCP；用 Playwright 做可达性验证；做 API 后端可达性诊断并自动 fallback。

### 国内优秀 README / 传播案例

**15. Pake / DrawDB / Cherry Studio / LobeChat / 《Hello 算法》**
- Pake：首屏一句话 + 平台图标 + 三条路径（小白/开发/折腾用户）。
- DrawDB：README 极短，一张主图 + 三行启动命令。
- Cherry Studio：README 顶部固定「下载 | 文档 | 社区」铁三角。
- LobeChat：一键部署到 Vercel 按钮 + Docker Compose + GIF。
- 《Hello 算法》：动画图解、一键运行、多语言代码；作者持续在 B站/知乎/GitHub 更新。

**Netfix 借鉴**：
1. 首屏一句话 + 一张结果图。
2. 三层用户分流（小白下载 / 开发者命令 / 极客定制）。
3. 安装命令可复制（brew / docker / 一键脚本）。
4. 中英文 README 顶部铁三角。
5. 用病例/案例建立社区（`cases/` 目录公开、可搜索）。

### 竞品总结：5 大共性痛点与 5 大机会点

**国内代理/网络工具市场 5 大共性痛点**：
1. 第一公里门槛高：下载靠 GitHub、安装要关 gatekeeper、注册要外区账号。
2. 配置即门槛：订阅链接、规则文件、MITM 证书、环境变量。
3. 错误信息不可读：JSON/YAML 解析报错、内核启动失败。
4. 代理残留与副作用：退出后系统代理没清、DNS 被改、国内软件变慢。
5. AI 工具网络适配碎片化：每个 AI 客户端都要单独配代理/base_url/API Key。

**Netfix 5 大机会点**：
1. 诊断优先，连接其次：别人卖「能不能连」，Netfix 卖「为什么连不上+怎么修」。
2. 国产环境原生适配：国内下载镜像、中文报错、自动清理副作用。
3. AI 工具一站式网络适配：把 Cursor/Claude Code/Kimi Code/Codex 需求封装成规则模板。
4. MCP 化输出：把诊断和修复能力暴露成 MCP tool。
5. 小白可执行的修复：分 Tier 自动/半自动执行，不是给一堆命令让用户复制。

**最应该差异化定位的方向**：
> **「AI 时代的 macOS 网络诊断与修复中枢」**。
> 不跟 Clash/Hiddify 拼协议支持，不跟 Surge 拼规则高级度；专注解决「代理已开但 AI/Codex/GitHub 还是连不上」这一高频高痛场景。

---

## 五、功能闭环审计

逐项审查 Netfix 功能是否真能让小白闭环。

| 功能 | 成熟度 0-10 | 小白可用 | 最大失败点 | 应该怎么改 | 涉及文件 | 验收标准 |
|------|------------|---------|-----------|-----------|---------|---------|
| 一行安装 Mac App | 5 | 否 | Gatekeeper 拦截 + App 装到 `~/Applications` 用户找不到 | 脚本自动处理 quarantine 或清晰引导；安装后 `open -R` 高亮 | `scripts/install_mac_app_from_github.sh` | 用户复制命令后能在 Launchpad 找到 App 并打开 |
| unsigned App 首次打开 | 4 | 否 | 系统弹窗「无法验证开发者」，用户直接移到废纸篓 | README 加图文步骤；脚本提前解除 quarantine（需确认） | `README.md`、安装脚本 | 80% 小白能按提示打开 App |
| 代理参数粘贴 | 7 | 中 | 不知道复制什么；两个检查按钮顺序混乱 | onboarding 引导复制来源；改为线性向导 | `gui/macos/Sources/Views/ProxySetupView.swift` | 用户知道从服务商后台复制哪一行 |
| 格式自动识别 | 7 | 中 | `host:port:user:pass` 默认 HTTP，SOCKS5 用户会错 | 协议自动探测或强制确认 | `netfix/residential_proxy.py`、`ProxySetupView.swift` | 90% 常见格式一次识别正确 |
| 保存到 Keychain | 8 | 是 | 失败时提示不够中文 | 包装 Keychain 访问错误 | `netfix/keychain.py` | 密码不落盘、不进日志 |
| 预检 | 7 | 中 | 「检查」和「保存并测试」两个按钮让人困惑 | 合并为线性流程：粘贴→检查→保存 | `ProxySetupView.swift` | 用户明确知道下一步该点什么 |
| 部署系统代理 | 6 | 中 | 部署确认框没说清影响范围 | 明确列出 Safari/Chrome/微信/钉钉等都会走代理 | `ProxySetupView.swift`、`residential_proxy.py` | 用户确认前知道所有 App 会受影响 |
| 回滚 | 7 | 中 | Dashboard「恢复」按钮永远可用，状态不明 | 根据代理状态动态显示 | `DashboardView.swift`、`netfix/fix_engine.py` | 一键回滚到上一次系统代理设置 |
| 代理健康监控 | 6 | 中 | 状态卡片只显示前 3 项，失败时看不到详情 | 失败卡片默认展开 | `DashboardView.swift` | 用户能看到哪个节点/服务异常 |
| IPv6 问题提示/处理 | 6 | 中 | Tier 2 修复需要确认，但 MCP 路径曾有参数遗漏疑虑 | 修复确认参数透传；给人话提示 | `netfix/mcp_server.py`、`fix_engine.py` | 能识别并提示 IPv6 导致的连接问题 |
| AI 问答 | 5 | 否 | 默认关闭、配置步骤多、缺 preset 向导 | 首次启用向导；一键选 DeepSeek/Kimi/MiniMax | `gui/macos/Sources/Views/SettingsView.swift`、`netfix/settings.py` | 小白 3 步内开启 AI 解释 |
| 不接 API Key 的离线解释 | 7 | 是 | 本地解释模板有限 | 扩展 `_CAUSE_EXPLANATIONS` | `netfix/explain.py` | 不接 Key 也能给出人话结论 |
| 接 Kimi/MiniMax/DeepSeek/OpenAI-compatible API | 6 | 否 | 不知道选哪个 provider、base_url/model 怎么填 | 提供 preset 向导；默认填好官方 endpoint | `netfix/llm_provider.py`、`SettingsView.swift` | 选供应商后自动填 endpoint/model |
| MCP for Codex | 7 | 中 | 只服务 Codex，Kimi/Claude/Cursor 用户被忽略 | 统一 MCP 入口，支持多宿主 | `scripts/install_mcp.sh`、`install_codex_mcp_from_github.sh` | Codex/Kimi/Claude/Cursor 都能拿到配置 |
| MCP for Kimi / Claude / Cursor | 5 | 否 | 配置片段打印到 stderr，小白不知道贴到哪 | 输出到 stdout 并说明粘贴路径 | `scripts/install_mcp.sh` | 用户拿到可直接粘贴的 YAML 和路径 |
| GitHub issue 脱敏报告 | 7 | 是 | 缺少主动防 paste 机制 | 提供 `sanitize_user_text()` 并集成到导出/分享流 | `netfix/redaction.py`、`report.py` | 导出的 support bundle 不含密码 |
| 一键卸载 | 5 | 否 | `--uninstall` flag 不会出现在复制命令里 | README 和脚本结尾都打印卸载命令 | `scripts/install_mac_app_from_github.sh`、README | 用户知道怎么卸载 |
| 日志查看 | 6 | 中 | 日志入口不明显 | Dashboard 增加「查看日志」按钮 | `DashboardView.swift` | 用户能找到并复制日志 |
| 错误复制 | 5 | 否 | 错误横幅只映射 3 种错误，其他露技术码 | 建立完整错误码到人话映射表 | `DashboardView.swift`、`APIClient.swift` | 所有常见错误都有中文解释 |

---

## 六、AI 交互体验深挖

用户明确吐槽：「问 AI 很费劲，没有一键配置 API，不知道需不需要 harness，不知道 MiniMax API 怎么接。」

### 现状问题

**1. API Key 配置不好找**
- 路径：主界面底部「设置」→ 顶部标签「AI」→ 打开「启用」开关 → 选择供应商 → 粘贴 API Key → 保存。
- 主界面没有任何「配置 AI」的快捷入口，必须进设置。
- 默认 `llmEnabled = false`，所有 AI 功能都不可用。

**2. Kimi / MiniMax / DeepSeek / OpenAI-compatible 配置不清楚**
- Picker 列出供应商，但「OpenAI-compatible」被隐藏在「自定义模型」里。
- 高级设置折叠面板暴露了 Base URL、模型、密钥名称、备用链路、预算、每小时请求上限，信息过载。
- MiniMax preset 是 `base_url=https://api.minimaxi.com/v1`、`model=MiniMax-M3`，但 UI/CLI 没有引导选择 preset。
- 「导入 DeepSeek 侧车 Key」术语晦涩。

**3. 没有一键粘贴 API Key 配置**
- 流程：用户自己从供应商后台复制 Key → 手动切回 Netfix → 在 SecureField 粘贴 → 点保存。
- 没有「从剪贴板自动检测 Key」「一键粘贴并自动识别供应商」。

**4. AI 回答与诊断上下文绑定**
- 已绑定：`explain_with_llm()` 把完整 `report` 先 `redact_report()` 再塞进 prompt。
- 但 `upload_consent` 默认 `"ask_each_time"`，每次都要 `upload_confirmed=true`，流程太长。

**5. 没有固定快捷问题**
- `question` 字段完全开放，没有预设快捷问题列表。

**6. local rule engine 优先，LLM 只是翻译和补充**
- 已实现：`explain.py` 本地规则字典 `_CAUSE_EXPLANATIONS` 直接生成中文结论。
- 但 UI 上没有明确告诉用户「这是本地解释」vs「这是云端 AI 解释」。

### AI 交互改造方案

**1. 界面文案与入口**
- 主界面增加「让 AI 解释」快捷按钮（仅在诊断失败时出现）。
- Dashboard 错误横幅增加「这是什么意思？」按钮，点击触发 AI 解释当前错误。
- 设置页「AI」标签增加「简单模式」默认视图：启用开关 + 供应商选择 + API Key 输入 + 测试按钮。
- 「高级模式」折叠：Base URL / 模型 / 备用链路 / 预算。

**2. 状态流**
- 未配置 API Key 时：AI 按钮显示「未配置 API Key，使用本地解释（可在设置中开启云端 AI）」。
- 已配置但未启用：提示「AI 解释已关闭，点击开启」。
- 已启用：直接显示「用 AI 解释当前诊断」。
- 首次点击上传时弹出隐私说明：「发送前会先删除 IP、代理密码、API Key，仅发送脱敏后的诊断结论和少量检测指标。」提供选项：每次问我 / 总是发送 / 从不发送。

**3. 配置字段**
- 简单模式字段：`enabled`、`provider`、`api_key`、`test`。
- 选择供应商后自动填充 `base_url` 和 `model`：
  - DeepSeek：`https://api.deepseek.com`、`deepseek-v4-flash`
  - Kimi：`https://api.moonshot.cn`、`moonshot-v1-128k`
  - MiniMax：`https://api.minimaxi.com/v1`、`MiniMax-M3`
  - Qwen：`https://dashscope.aliyuncs.com/compatible-mode/v1`、`qwen-max`
  - 自定义：用户手动填 `base_url` + `model` + `api_key`
- 增加「粘贴剪贴板中的 Key」按钮，尝试自动识别供应商（如 Key 前缀 `sk-` 不一定是 DeepSeek，需结合用户选择）。

**4. 隐私说明**
- 设置页常驻说明：「AI 看报告时，会先删除你的 IP、代理密码、API Key 等敏感信息。发送给供应商的内容仅包含脱敏后的诊断结论和少量检测指标。」
- 提供脱敏强度选择：默认 / 严格。

**5. 固定快捷问题**
- 在 AI 解释面板提供 4 个快捷问题：
  1. 「这是什么问题？」
  2. 「应该怎么修？」
  3. 「我的代理参数对吗？」
  4. 「怎么恢复原来的网络？」

**6. 本地规则优先，LLM 只是翻译和补充**
- 始终先返回本地规则解释。
- 云端 AI 返回时标注来源：「本地规则结论」/「云端 AI 补充解释」。
- 若云端 AI 不可达，自动 fallback 到本地规则，并提示「云端 AI 暂不可用，以下为本地规则解释」。

---

## 七、MCP / Agent 国内使用场景审计

### 现状

**Codex 一行 MCP 安装**：
- `install_codex_mcp_from_github.sh` 对已有 Codex CLI 的用户基本可用。
- 默认拉 `main` 分支，版本不固定；覆盖旧 MCP 时没有备份；只服务 Codex。

**Kimi Code 接入**：
- `install_mcp.sh` 对 Kimi 只打印一段 stdio 配置到 stderr，不会自动写入。
- 配置片段和命令混在一起，小白不知道贴到哪。

**Claude Desktop / Claude Code 接入**：
- README 有配置路径说明，但没有自动写入脚本。

**Cursor 接入**：
- README 有 `.cursor/mcp.json` 说明，但同样没有自动写入。

### 核心问题

1. **MCP 输出给模型不够友好**：`_call_tool` 把所有结果 `json.dumps` 后塞进单条 `text` content，大报告容易超 token。
2. **缺少关键只读工具**：`evidence_chain`、`list_fixes`、`sanitized_report`、`proxy_credential_doctor` 都没有。
3. **Agent 调 netfix 时如何避免乱改系统设置**：`netfix_fix_issue` 已通过 `_fix_issue_for_mcp` 走 `api._execute_confirmed_fix`，Tier 2 必须 `confirmed=true` + `confirmation="APPLY_SYSTEM_FIX"`；`flush_dns`/`renew_dhcp`/`disable_ipv6` 默认 `dry_run=True`。
4. **多宿主支持不均衡**：Codex 有自动注册，Kimi/Claude/Cursor 只有手动配置片段。

### MCP 下一版工具清单和 schema 建议

**新增只读工具**（安全，Agent 可放心调用）：

```json
{
  "name": "netfix_evidence_chain",
  "description": "返回从诊断探针到根因推理再到修复建议的完整证据链",
  "inputSchema": {
    "type": "object",
    "properties": {
      "report_id": { "type": "string", "description": "可选，留空用最新报告" }
    }
  },
  "annotations": { "readOnlyHint": true, "destructiveHint": false }
}
```

```json
{
  "name": "netfix_list_fixes",
  "description": "列出当前诊断报告中的可执行修复，按 Tier 分类，不执行",
  "inputSchema": {
    "type": "object",
    "properties": {
      "tier": { "type": "string", "enum": ["1", "2", "3", "all"], "default": "all" }
    }
  },
  "annotations": { "readOnlyHint": true, "destructiveHint": false }
}
```

```json
{
  "name": "netfix_sanitized_report",
  "description": "返回已脱敏、可安全上传到 LLM 或 GitHub issue 的诊断报告",
  "inputSchema": {
    "type": "object",
    "properties": {
      "level": { "type": "string", "enum": ["balanced", "strict"], "default": "strict" }
    }
  },
  "annotations": { "readOnlyHint": true, "destructiveHint": false }
}
```

```json
{
  "name": "netfix_proxy_credential_doctor",
  "description": "专项诊断代理认证失败：用户名错误、密码过期、格式问题、407 响应",
  "inputSchema": {
    "type": "object",
    "properties": {
      "input": { "type": "string", "description": "代理连接参数（会被脱敏）" }
    }
  },
  "annotations": { "readOnlyHint": true, "destructiveHint": false }
}
```

**现有工具改进**：
- `netfix_report`、`netfix_explain` 增加 `format` 参数：`summary`/`card`/`full`。
- `netfix_fix_issue` 的 `_build_argv` 保持与 `_fix_issue_for_mcp` 一致（当前 `_call_tool` 已特判，但 `_build_argv` 中死代码应补全 `confirmed`/`confirmation` 以消除误导）。
- `netfix_proxy_switch` 增加 `dry_run` 参数，允许先预览切换结果。

**多宿主 MCP 配置自动化**：
- **Codex**：`codex mcp add` 保持不变，覆盖前备份旧配置。
- **Kimi Code CLI**：检测到 `kimi` 命令后，尝试写入 `~/.kimi/mcp.json`，失败时打印片段。
- **Claude Desktop**：自动写入 `~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers` 段。
- **Cursor**：自动写入 `~/.cursor/mcp.json` 的 `mcpServers` 段。

---

## 八、安全、合规、信任审计

### 现状检查

**README 和 App 是否有危险表达**：
- 原 README 有「合法代理参数」「Codex / ChatGPT / GitHub 突然连不上」「xray / sing-box / mihomo / Clash」等表述，容易被理解为代理/VPN 工具。
- `residential_proxy.py` 文件名含 `residential proxy`，合规审查敏感。
- 本次已调整 README 表述，弱化风险词汇，强化「本地网络诊断与配置管理助手」定位。

**是否过度承诺代理质量**：
- README 已明确：不卖代理、不内置节点、不承诺第三方服务质量、不承诺特定出口质量。
- 需继续检查 `netfix/residential_proxy.py` 和 UI 文案中是否有「住宅 IP」「切换到住宅 IP 节点」等表达。

**是否可能被理解为规避平台规则**：
- 当前 README 明确：严格遵守第三方平台规则，不做任何形式的规避。
- 仍需避免：反检测、养号、防封、绕过封锁等词汇。

**是否说明「不卖代理、不提供节点、不保证第三方服务」**：
- ✅ 已说明，多处重复。

**是否说明密码存在 Keychain**：
- ✅ 已说明。

**是否说明不会上传原始报告/API Key**：
- ✅ 已说明。

**是否防止用户把代理密码贴到 issue**：
- README、模板、CONTRIBUTING、SECURITY 都有提醒。
- 代码层面仅保存报告时自动脱敏，缺少主动扫描用户输入文本的功能。

**是否有一键卸载和恢复说明**：
- 脚本支持 `--uninstall` 但 README 之前不够醒目。
- 本次 README 已增加卸载命令和 `python3 netfix.py rollback` 说明。

**是否有签名/公证状态说明**：
- ✅ 有说明，本次 README 已把警告提前到首屏下方。

### P0/P1/P2 问题清单

**P0（必须立即处理）**：
1. `residential_proxy.py` 文件名含敏感词，建议改为 `system_proxy.py` 或 `proxy_apply.py`。
2. README/App 中所有「住宅 IP」表述必须替换为中性描述，如「当前出口属于数据中心 ASN」。
3. Gatekeeper 拦截没有清晰引导，用户可能直接卸载。
4. 部署确认框未说明「所有 App 都会走代理」，可能导致用户误操作。
5. Dashboard 错误提示只映射 3 种错误，大量技术码直接暴露。

**P1（7 天内处理）**：
1. `SECURITY.md`、`CONTRIBUTING.md` 全英文，国内用户跳过；提供中文版。
2. 安装脚本默认拉 `main` 分支，应默认 pin release tag。
3. Kimi/Claude/Cursor MCP 配置只打印片段，需给出明确粘贴路径和自动写入。
4. App「Agent」标签改名为「AI 编程助手」，README 同步更新。
5. AI 设置缺少「简单模式」，信息过载。

**P2（30 天内处理）**：
1. 缺少主动检测用户把密码贴到 issue 的功能。
2. 隐私披露只在首次启动出现，之后找不到入口。
3. 权限标签把系统权限和隐私数据设置混在一起，需拆分。
4. `proxy_bridge` 本机桥接无认证，需补充安全说明或可选本地 token。

---

## 九、路线图

### 48 小时内：只做最能提升小白可用性和 GitHub 转化的事

| 目标 | 文件/模块 | 验收标准 | 测试方式 | 用户价值 |
|------|----------|---------|---------|---------|
| README 首屏只讲「粘贴代理上网」 | `README.md` | 首屏只有 1 个主 CTA，警告块醒目，Agent/MCP 折叠 | `test_readme_llm_examples.py`、`test_marketing_claims_check.py` | 5 秒看懂产品 |
| App 安装命令下方给出卸载命令 | `README.md`、`install_mac_app_from_github.sh` | README 有卸载命令；脚本结尾打印卸载提示 | `test_open_source_readiness.py` | 用户敢尝试 |
| 修复错误码到人话映射 | `gui/macos/Sources/Views/DashboardView.swift`、`APIClient.swift` | 至少覆盖账号密码错、节点不可用、DNS、App 错误 4 类 | 手动跑 App，输入错误代理参数 | 用户知道下一步 |
| 代理配置流程线性化 | `ProxySetupView.swift` | 粘贴→检查→保存→部署，下一步未解锁时置灰 | UI 测试/手动 | 减少误操作 |
| MCP 配置输出到 stdout 并说明粘贴路径 | `scripts/install_mcp.sh` | Kimi/Claude/Cursor 配置片段和路径清晰打印 | `test_open_source_readiness.py` | Agent 用户 1 分钟接好 |

### 7 天内：真实截图/GIF、case、AI 配置、MCP 配置复制、错误文案

| 目标 | 文件/模块 | 验收标准 | 测试方式 | 用户价值 |
|------|----------|---------|---------|---------|
| 制作 3-5 个真机 GIF | `assets/github/` | GIF 前 3 帧展示核心价值，< 5 MB | 视觉检查 | 降低理解门槛 |
| 新增 3 个真实 case | `cases/` | 按 TEMPLATE.md 提交，已脱敏 | `pytest` | 建立信任证据 |
| AI 设置「简单模式」 | `SettingsView.swift`、`settings.py` | 默认只显示开关/供应商/Key/测试 | UI 测试 | 小白能配 AI |
| App「Agent」标签改名 | `SettingsView.swift`、README | 改为「AI 编程助手」 | `test_macos_mcp_setup_ui.py` 同步更新 | 降低认知门槛 |
| MCP 配置复制按钮说明 | `SettingsView.swift` | Codex/Kimi/Claude/Cursor 按钮旁有气泡说明 | UI 测试 | 用户知道贴到哪 |
| 错误文案映射表覆盖 20 个常见错误 | `DashboardView.swift` | 单元测试覆盖 | 新增测试 | 用户不被技术码吓退 |

### 30 天内：签名公证、Homebrew、release 自动化、Claude/Kimi/Cursor MCP 指南、更多真实 case

| 目标 | 文件/模块 | 验收标准 | 测试方式 | 用户价值 |
|------|----------|---------|---------|---------|
| Apple Developer ID 签名 + 公证 | `gui/macos/`、CI workflow | 下载后不再弹 Gatekeeper 拦截 | 干净机器 QA | 普通用户敢双击 |
| Homebrew Cask | `Casks/netfix.rb`、CI | `brew install --cask netfix` 可用 | 手动/CI | 国内用户熟悉的安装方式 |
| Release 自动化 | `.github/workflows/release.yml` | tag push 后自动签名、公证、发 release | CI 跑通 | 降低维护成本 |
| Claude/Kimi/Cursor MCP 自动写入 | `scripts/install_mcp.sh` | 检测到宿主后自动写入配置或给出明确片段 | 手动测试 | Agent 用户全覆盖 |
| 累积 10 个真实 case | `cases/` | 覆盖代理部署、AI 工具断线、VPN 冲突、DNS 等 | `pytest` | SEO 和社区信任 |

### v0.3.0 应该发什么能力

1. **签名公证后的 macOS App**：普通用户能双击安装，不再被 Gatekeeper 拦截。
2. **Homebrew 一键安装**：`brew install --cask netfix`。
3. **App 内代理配置四步向导**：粘贴 → 检查 → 保存 → 部署，线性流程。
4. **AI 解释简单模式**：3 步开启 DeepSeek/Kimi/MiniMax。
5. **多宿主 MCP 自动配置**：Codex/Kimi/Claude/Cursor 一键复制/写入。
6. **错误码到人话映射表**：覆盖 20+ 常见错误。
7. **新增 MCP 只读工具**：`netfix_evidence_chain`、`netfix_list_fixes`、`netfix_sanitized_report`。
8. **10 个真实脱敏 case**：建立病例库。

### v1.0 什么条件下才配叫正式产品

1. **App 签名公证完成**，用户从官网/Homebrew 下载后无需命令行即可安装。
2. **小白用户完整闭环率 ≥ 70%**：从 GitHub 首页到成功让 Mac 上网，不求助命令行。
3. **AI 解释接入率 ≥ 50%**：用户能独立配置至少一个国内 LLM provider。
4. **MCP 宿主覆盖主流**：Codex / Kimi / Claude Desktop / Cursor 都有官方接入文档或自动配置。
5. **错误提示人话化 ≥ 90%**：不再暴露 `fix_command_failed` 等技术码。
6. **安全合规无 P0 问题**：无危险表述，无密码泄露风险，有完整隐私说明。
7. **病例库 ≥ 30 个真实 case**：覆盖常见代理/AI 工具/网络故障场景。
8. **Star ≥ 1k 且有持续社区贡献**：issue、case、文档翻译有人持续参与。

---

## 十、本次直接改动记录

本轮审计中，我做了以下低风险、高收益的改动：

### 1. `README.md` 重写

**改动理由**：
- 首屏定位模糊，同时出现 App 安装和 Codex MCP 两个命令，小白不知道该复制哪个。
- 「已有合法代理参数」像法律声明，「macOS 本地网络急诊工具」像系统急救软件。
- QA 版未签名警告不够醒目，Gatekeeper 拦截没有图文引导。
- AI 配置、MCP 配置说明分散，Kimi/Claude/Cursor 用户找不到粘贴位置。

**主要改动**：
- 首屏 tagline 改为「买了代理不会配？粘贴一行，让 Mac 安全上网。」
- 移除首屏 `MCP ready` badge，把 MCP 内容折叠到二级。
- 新增醒目的 ⚠️ 当前版本说明区块，明确 DMG 未签名/未公证及「仍要打开」步骤。
- 新增「三步让 Mac 上网」区块，放在首屏下方。
- 新增「它解决什么问题」场景表，覆盖小白真实痛点。
- 「当前能怎么用」改为 App 安装优先，源码路径次之；增加卸载命令。
- 「接进 Codex / Kimi / Claude / Cursor」提前，明确 App 内路径和配置粘贴位置。
- AI 问答部分增加「建议新手直接选」供应商对照表。
- FAQ 增加「不接 API Key 能用吗」对照表。

**验证命令**：
```bash
python3 -m pytest tests/test_readme_llm_examples.py tests/test_marketing_claims_check.py tests/test_open_source_readiness.py tests/test_macos_mcp_setup_ui.py -v
```

**结果**：17 个相关测试全部通过。

**风险**：README 结构和文案改动较大，但所有测试约束字符串均已保留；未夸大产品能力；未改变 unsigned QA DMG 的定性。

### 2. `scripts/install_mcp.sh` 输出改进

**改动理由**：
- 原脚本把 Kimi 通用配置打印到 stderr，小白看不到。
- 没有告诉用户 Codex 注册后下一步该做什么。
- 没有说明 Kimi/Claude/Cursor 配置该粘贴到哪个文件。

**主要改动**：
- Codex 注册成功后打印明确的 Next steps（重启 Codex、测试命令、验证命令）。
- Kimi/Claude/Cursor 配置用 `---` 分隔块输出到 stdout，并给出每个宿主的具体配置文件路径：
  - Kimi：`~/.kimi/mcp.json`
  - Claude Desktop：`~/Library/Application Support/Claude/claude_desktop_config.json`
  - Cursor：`~/.cursor/mcp.json` 或 `<project-root>/.cursor/mcp.json`
- 脚本结尾增加直接测试 MCP server 的命令提示。

**验证命令**：
```bash
python3 -m pytest tests/test_open_source_readiness.py -v
```

**结果**：相关测试通过；`test_current_repository_claims_pass`  marketing claims check 通过。

**风险**：输出格式变化，但所有测试要求的字符串（`codex mcp add netfix`、`Automatic Kimi MCP registration is not enabled`、`netfix/mcp_server.py`、`--dry-run`、`cd /tmp`）均保留。

### 3. `AGENTS.md` 增加人话解释和下一版 MCP 工具预告

**改动理由**：
- 「Tier 1/2/3」对小白是黑话。
- `triage`/`doctor`/`kb` 子命令没有更直白的别名。
- MCP 工具列表缺少 `evidence_chain`、`list_fixes` 等规划中的只读工具说明。

**主要改动**：
- Tier 解释改为「可自动执行 / 需用户确认 / 只能手动」。
- 诊断优先顺序增加别名：`check`、`full-check`、`guide`。
- MCP 工具列表增加下一版计划增加的只读工具说明，并强调它们不会修改系统设置。

**验证命令**：
```bash
python3 -m pytest tests/test_open_source_readiness.py -v
```

**结果**：通过。

**风险**：AGENTS.md 是 Agent 工作手册，改动后 Agent 会收到更清晰的中文指引；未改变任何修复执行规则或安全边界。

### 4. 完整测试套件

**验证命令**：
```bash
python3 -m pytest -q
```

**结果**：406 passed, 1 skipped。

---

## 十一、最终判断

### 1. 现在是否值得开源？

**值得，但要控制预期。**

Netfix 的源码开源价值很高：诊断逻辑、脱敏规则、MCP 封装、Keychain 安全存储都已经有工程厚度，值得被社区看到和贡献。但**现在不能把 Netfix 包装成「普通用户稳定可用的正式产品」**。v0.2.0-qa.1 的 DMG 还没签名公证，安装脚本对小白来说门槛仍然很高，App 内代理配置流程还像工程师调试面板。

建议开源策略：
- 继续开源源码，吸引开发者、AI Agent 用户、愿意贡献 case 的人。
- README 首屏明确标注 QA 预览版，不要暗示普通用户可以「闭眼安装」。
- 把「普通用户正式版」作为 v1.0 目标，而不是现在。

### 2. 国内用户会不会愿意 Star？

**会，前提是首屏和 GIF 讲清楚「粘贴一行让 Mac 上网」。**

国内开发者/AI 用户对「网络诊断」「AI 工具连不上」这个话题高度敏感，V2EX、少数派、B站、即刻都有传播空间。但 Star 转化取决于：
- 首屏 3 秒内是否让人看懂这是干嘛的。
- 是否有真机 GIF 展示三步流程。
- 是否有真实 case 让人产生「这问题我也遇到过」的共鸣。
- 是否不触发「代理/翻墙」的敏感联想。

目前 README 经过本次改写后，首屏定位已经清晰很多。下一步需要补上 GIF 和 5-10 个真实 case，传播才会真正松动。

### 3. 普通 Mac 用户现在能不能用？

**能，但很费劲。**

技术型 Mac 用户现在可以用：
- 复制 `curl | bash` 安装 App（但会卡在 Gatekeeper）。
- 去系统设置点「仍要打开」。
- 在 App 里粘贴代理参数、检查、保存、部署。
- 出问题时看 JSON 或日志。

但**不会命令行、不会看 JSON、不会配系统代理的小白用户**，现在大概率会在以下环节放弃：
1. 看到两个 `curl | bash` 不知道该复制哪个。
2. Gatekeeper 弹窗不敢点。
3. App 装到 `~/Applications` 但在 `/Applications` 找不到。
4. 两个检查按钮不知道该点哪个。
5. 保存后不知道还要再点「开始使用这台 Mac 上网」。
6. 部署后微信/网银也走代理，不知道怎么恢复。
7. 错误提示看到技术码直接放弃。

结论：**普通 Mac 用户现在能用，但体验不够产品化。**

### 4. 最影响传播的 5 个问题

1. **首屏定位混乱**：三种身份混在一起，小白 5 秒内不知道自己是目标用户。（已部分修复 README）
2. **Gatekeeper 拦截没有解决**：未签名 App 是传播最大杀手，普通用户第一步就卡死。
3. **没有真机 GIF/截图**：README 只有概念图和流程图，没有「粘贴→检查→上网」的真实演示。
4. **App 内代理配置流程不线性**：两个检查按钮、保存后不出部署引导，小白反复误操作。
5. **错误提示不够人话**：大量技术码暴露，用户不知道是该换密码、换节点还是重启 App。

### 5. 最值得做的 5 个创新

1. **「粘贴一行让 Mac 上网」的极简代理部署向导**：把四步流程做成 App 内的线性 wizard，这是国内最大痛点，没有竞品真正做好。
2. **AI 工具网络适配层**：自动检测 Cursor/Claude Code/Kimi Code/Codex 需要访问的域名，生成最小化分流规则，解决「代理开了但 AI 工具不走」的问题。
3. **MCP 诊断工具链**：把 `evidence_chain`、`list_fixes`、`sanitized_report`、`proxy_credential_doctor` 做成只读 MCP 工具，让 Agent 能安全地追问和修复。
4. **病例库（cases/）产品化**：把脱敏真实 case 变成可搜索、可匹配的症状库，用户输入问题就能找到相似 case 和修复步骤。
5. **国产环境原生安装体验**：Homebrew Cask + 国内镜像下载 + 签名公证，把「第一公里门槛」降到普通用户敢点的程度。

### 6. 下一轮最应该先开发什么

**第一优先级（48 小时 - 7 天）**：
1. **Apple Developer ID 签名 + 公证**：这是普通用户敢用的前提，没有它，所有传播都会卡在第一步。
2. **App 内代理配置四步向导**：粘贴 → 检查 → 保存 → 部署，下一步未解锁时置灰，保存成功后自动高亮部署按钮。
3. **错误码到人话映射表**：至少覆盖账号密码错、节点不可用、DNS 失败、App 内部错误四类，让小白知道下一步该干嘛。
4. **真机 GIF**：3-5 个 GIF 展示「粘贴代理→检查→部署」「Codex 连不上→诊断→修复」「一键回滚」。

**第二优先级（7 - 30 天）**：
1. Homebrew Cask。
2. AI 设置「简单模式」。
3. 多宿主 MCP 自动配置（Kimi/Claude/Cursor）。
4. 新增 10 个真实脱敏 case。
5. `SECURITY.zh.md`、`CONTRIBUTING.zh.md`。

**第三优先级（v0.3.0 - v1.0）**：
1. 新增 MCP 只读工具链。
2. AI 工具网络适配层。
3. 病例库搜索与匹配。
4. 完整签名公证后的正式版发布。

---

## 附录：关键文件速查

| 文件 | 本次是否改动 | 审计结论 |
|------|------------|---------|
| `README.md` | ✅ 重写 | 首屏定位已清晰，但需补 GIF 和 case |
| `AGENTS.md` | ✅ 小幅改写 | Tier 解释更人话，增加 MCP 工具预告 |
| `scripts/install_mcp.sh` | ✅ 输出改进 | Kimi/Claude/Cursor 配置路径更清晰 |
| `scripts/install_mac_app_from_github.sh` | ❌ 未改动 | Gatekeeper/找不到 App/卸载入口是最大卡点 |
| `scripts/install_codex_mcp_from_github.sh` | ❌ 未改动 | 只服务 Codex，需统一多宿主入口 |
| `netfix/mcp_server.py` | ❌ 未改动 | 工具覆盖较全，但缺 evidence_chain 等只读工具 |
| `netfix/residential_proxy.py` | ❌ 未改动 | 文件名含敏感词，建议改名；格式识别较全 |
| `netfix/explain.py` | ❌ 未改动 | 本地规则解释可用，但缺快捷问题 |
| `netfix/settings.py` | ❌ 未改动 | AI 默认关闭，缺简单模式 |
| `gui/macos/Sources/Views/ProxySetupView.swift` | ❌ 未改动 | 流程不线性，两个检查按钮让人困惑 |
| `gui/macos/Sources/Views/DashboardView.swift` | ❌ 未改动 | 错误提示只映射 3 种，状态指示不清 |
| `gui/macos/Sources/Views/SettingsView.swift` | ❌ 未改动 | AI 配置信息过载，Agent 标签不直观 |

---

*本文档基于对 README.md、AGENTS.md、安装脚本、Netfix 核心代码、macOS GUI Swift 文件、国内竞品及开源传播案例的深度审读生成。所有结论均绑定到具体文件、界面、命令或用户动作。*
