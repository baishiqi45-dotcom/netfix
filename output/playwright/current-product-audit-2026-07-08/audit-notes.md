# Netfix 产品结构冷审 - 2026-07-08

## 审计范围

- 产品：`/Users/qibaishi/Desktop/网络` 下的 Netfix。
- 方式：主线程只读审计 + 5 个只读子智能体并行审计。
- 证据：README、AGENTS、CLI parser、HTTP API、MCP tools、SwiftUI App 源码、Web dashboard 当前截图。
- 本轮未修改产品代码、未执行任何修复命令。

## 截图证据

- `01-web-dashboard-home.png`：当前 Web dashboard 首屏。
- `02-web-dashboard-secondary-panels.png`：打开“网络线路”和“AI 解释”后的二级面板。

## 一句话判决

Netfix 不是缺功能，而是缺一个强制执行的产品层级。现在的真实核心应该是“已有代理参数部署与 macOS 网络自救”，但文档、CLI、Web、App、HTTP、MCP 同时把代理部署、AI 工具诊断、Agent 集成、LLM 解释、发布门禁、内部 RPC 都拿出来说，用户无法判断哪个是主路径，哪个只是高级能力或兼容层。

## 已经变好的部分

- SwiftUI 欢迎页已经从“AI 开发工具断线急救”改成更普通用户的“网络出问题了？我帮你看看”（`gui/macos/Sources/Views/WelcomeView.swift:17`）。
- 代理设置页已经把“检查并保存”和“开始使用代理”拆清楚，并用中文确认弹窗替代旧的英文确认短语体验（`gui/macos/Sources/Views/ProxySetupView.swift:109`、`:148`、`:200`）。
- Web 首屏比旧版收敛：默认只显示“一键检查”和“需要时再用”，AI 与线路入口被放到右侧二级区（`gui/web/index.html:255`、`:319`）。

这些是正确方向。但主产品叙事和能力分层还没真正锁住。

## P0 问题

### P0-1：主语分裂，北极星没锁死

证据：

- README 首句是“买了代理不会配 Mac？粘贴参数”（`README.md:11`）。
- Web 首屏标题是“AI 工具连不上，一键查原因并给修法”（`gui/web/index.html:243`）。
- AGENTS 标准入口是 `python3 netfix.py codex --json`（`AGENTS.md:15`）。
- CLI 描述是 “Offline-first network self-rescue agent for macOS.”（`netfix/cli.py:889`）。

这四句话都不是错的，但不能同时做第一层。用户第一次接触时会摇摆在三个任务之间：我要部署代理、我要诊断 AI 工具、还是我要给 Agent 装网络工具。

建议：

- 顶层定位固定为：`把已有 HTTP/SOCKS 代理安全接入这台 Mac，并在网络出问题时告诉你哪里坏了、怎么恢复。`
- App/README 第一屏只讲普通用户路径。
- Agent/MCP/HTTP/LLM 全部标为增强层或开发者层。

### P0-2：README 第一层混入太多受众

证据：

- 普通用户三步路径在 `README.md:23`。
- AI 解释、环境变量、HTTP curl、MCP 工具名从 `README.md:121` 开始进入。
- 开发者与 Agent 入口在 `README.md:168`。
- 开源发布门禁和 release 命令在 `README.md:299` 之后。

问题不是内容无用，而是层级错误。普通用户还没建立主路径，就被 LLM、MCP、curl、源码运行、Swift build、release audit 拉走。

建议 README 第一层只保留：

1. Netfix 是什么。
2. 适合谁，不适合谁。
3. 下载/打开 App。
4. 粘贴参数、预检、启用、恢复。
5. 支持与不支持的参数格式。
6. 安全边界。
7. 入口选择：普通用户 / Agent / 开发者 / 维护者。

其他内容拆到 `docs/AGENT.md`、`docs/API_MCP.md`、`docs/REPORT_SCHEMA.md`、`docs/RULE_AUTHORING.md`、`RELEASE.md`。

### P0-3：文档承诺和实现漂移，入口可信度受损

证据：

- AGENTS 说 `check/full-check/guide` 是别名（`AGENTS.md:77`），但 parser 没有这些命令，实际只有 `triage/doctor/kb`（`netfix/cli.py:916`、`:918`、`:945`）。
- README 示例写 `python3 netfix.py explain --provider deepseek --json`（`README.md:136`），实际 `explain` 没有 `--provider` 参数（`netfix/cli.py:942`）。
- README 里的 `/llm/providers` 示例是 POST，但 API 实现是 GET；`/llm/explain` 文档路径和实现里的 `/explain_llm` 不一致（`netfix/api.py:1174`、`:1392`）。
- 本轮实测 `python3 netfix.py codex --json` 在当前环境报 UTF-8 decode error，而它被 README/AGENTS 当作标准入口。

这是 P0，因为 Netfix 的承诺是“Agent 先跑 netfix，再读 JSON”。如果标准入口、示例和实现漂移，产品信任直接掉。

建议：

- 要么补实现别名，要么删文档别名。
- 修正 `explain --provider` 和 HTTP API 示例。
- 加一个 release gate：README/AGENTS 中每条命令必须在测试里 smoke。
- 修 `codex --json` 当前 UTF-8 decode 失败。

### P0-4：CLI/API/MCP 像三代产品并存

证据：

- CLI 平铺 19 个命令（`netfix/cli.py:907`）。
- HTTP `/capabilities` 和 `/run` 能力边界不一致；`/capabilities` 暴露更多命令，`/run` 又只允许部分命令（`netfix/api.py:698`、`:793`、`:1233`）。
- MCP 同时有旧 `netfix_fix_issue`、新 `netfix_apply_fix`、快捷修复工具、底层探针工具（`netfix/mcp_server.py:62`、`:95`、`:139`、`:275`）。
- AGENTS 同时说 CLI 标准入口和 MCP 注册方式（`AGENTS.md:117`）。

建议统一模型：

- 普通用户：只暴露 `Netfix.app`。
- Agent：首选 MCP，诊断 `netfix_codex`，修复 `netfix_list_fixes → netfix_dry_run_fix → netfix_apply_fix`。
- 开发者 fallback：CLI，标准 `netfix codex --json` / `netfix triage --json`。
- HTTP：定义为 App 私有本地 API；`/run` 标兼容/调试，不作为主公共协议。
- 做一张权威能力矩阵：能力、App 入口、CLI、HTTP typed endpoint、MCP tool、read-only、是否需确认。

### P0-5：首屏视觉虽收敛，但仍在分叉前暴露二级复杂度

截图 `01-web-dashboard-home.png` 显示首屏已经清爽：一键检查 + 右侧“需要时再用”。但 `02-web-dashboard-secondary-panels.png` 一打开右侧二级入口，就同时出现：

- AI 状态、费用保护、问题输入、高级设置。
- 线路输入、检测场景、保存后看护。
- 批量导入、本机转发、后台看护、已保存线路和高级操作。

这说明复杂度只是被折叠，不是被分层。线路、AI、监控、桥接、批量导入不是同一层任务。

建议：

- “我有自己的网络线路”只进入一个任务流：粘贴一条参数 → 预检 → 保存 → 开始使用。
- 批量导入、桥接恢复、自动看护、已保存线路管理全部移到“高级线路管理”独立页面。
- “AI 解释”只依附于已有诊断结果，不和 provider 设置同屏出现；provider 设置放 Settings。

## P1 问题

### P1-1：`proxy` 这个词在不同地方含义不一致

- README 功能表把“代理粘贴部署”的开发者接口写成 `proxy/proxy-monitor/proxy-switch`（`README.md:276`）。
- CLI `proxy` 实际是代理核心专项诊断，不是粘贴、保存、部署（`netfix/cli.py:373`）。

建议把能力命名拆开：

- `proxy diagnose`
- `proxy precheck`
- `proxy save`
- `proxy apply`
- `proxy monitor`
- `proxy switch`

保留旧命令兼容，但文档只推荐新语义。

### P1-2：CLI help 是命令清单，不是入口设计

`python3 netfix.py --help` 直接列 19 个子命令。对 Agent/开发者还行，对新手没有 `Start here`。

建议加 epilog：

```text
Start here:
  App users: open Netfix.app and paste HTTP/SOCKS proxy parameters.
  Agent/Codex users: netfix codex --json
  General terminal triage: netfix triage --json
  Show last report: netfix report

Advanced:
  fix / rollback / proxy-switch / server may change state or run a local service.
```

### P1-3：human report 末尾追加 raw JSON，破坏“人话”承诺

证据：`Report.to_human()` 在末尾无条件追加完整 JSON（`netfix/report.py:186`）。

建议：

- 默认 human 输出只显示结论、原因、建议动作、关键证据。
- 完整 JSON 只在 `--json` 或 `--verbose` 下显示。
- 诊断项默认显示 display name，raw id 只进技术详情。

### P1-4：HTTP API 同时是 App 后端、公共 API、CLI 透传、调试工具

证据：GET/POST 路由覆盖 health/session/capabilities/report/services/events/logs/dashboard/support/environment/settings/llm/proxy/monitor/network/fixes/run 等大量路径（`netfix/api.py:1094`、`:1233`、`:1408`）。

建议：

- 分层命名：`/app/*` 私有 UI RPC，`/v1/*` 稳定公共 API，`/debug/run` 兼容调试。
- README 不宣传私有 RPC。
- token、origin、确认协议独立成开发者文档。

### P1-5：修复入口需要一个唯一权威动作模型

建议所有界面都表达成同一模型：

1. 列出可做动作。
2. 预览影响。
3. 按 Tier 判断是否需要确认。
4. 执行。
5. 自动复查。
6. 失败可恢复。

CLI、HTTP、MCP、App 卡片都只是在这个模型上的不同壳。

## P2 建议

- 做 `capabilities.yaml` 或 registry，标注 `core / advanced / internal / compat`，由它生成 README 功能表、HTTP `/capabilities` 和 MCP 工具描述。
- 诊断命令改成 profile registry：`codex/triage/doctor/layers/proxy/dns` 只是不同 profile，而不是散落在 CLI 函数里的重复组装。
- 把 `residential_proxy` 这种命名降噪为 `proxy_profiles` 或 `custom_proxy_profiles`。用户买的是“代理参数”，不是“住宅代理产品”。
- 让 `cases/` 反哺产品：常见症状、证据链、建议文案应驱动 UI 卡片，而不是继续新增命令。
- 不要马上扩 `ss://`、`vmess://`、Clash/sing-box 订阅；那会把产品拖成代理客户端竞品。
- 不要继续扩 LLM/provider/image 功能，先把本地规则解释、报告脱敏、恢复闭环做到可信。

## 推荐目标结构

```text
Netfix
├── 普通用户主线
│   ├── 打开 App
│   ├── 粘贴 HTTP/SOCKS 参数
│   ├── 本地预检
│   ├── 保存到 Keychain
│   ├── 确认启用系统代理/本机转发
│   └── 监控与恢复
├── 诊断
│   ├── quick / triage
│   ├── codex
│   ├── full / doctor
│   ├── layers
│   └── dns / wifi / tls / connectivity / proxy / services
├── 修复与恢复
│   ├── list
│   ├── dry-run
│   ├── apply
│   ├── apply-safe-all
│   └── restore network
├── 报告
│   ├── show
│   ├── explain local
│   ├── explain llm
│   ├── sanitize
│   └── logs
├── Agent / 开发者
│   ├── MCP v1
│   ├── CLI fallback
│   ├── HTTP private app API
│   └── schema / confirmation contract
└── 维护者
    ├── rules
    ├── cases
    ├── release gates
    └── signing / notarization / QA
```

## 下一步执行顺序

1. 写一张权威能力矩阵，先不改代码。
2. 重写 README 第一屏，只服务普通用户主线。
3. 修文档/实现漂移：别名、`explain --provider`、HTTP LLM 示例、`codex --json` UTF-8 失败。
4. 给 CLI help 加 `Start here`，并把高风险命令分组。
5. 把 Web/SwiftUI 的线路、AI、监控、桥接、批量导入拆成明确任务层级。
6. 再考虑命令树重构和 profile registry。
