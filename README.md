# netfix

[English README](README.en.md)

本地优先的 macOS AI/开发工具网络急诊产品。Codex / Claude Code / Cursor / OpenAI / GitHub / Kimi Code 连不上时，netfix 先判断是 DNS、系统代理、代理核心、节点、PAC/WPAD、IPv6、TLS 还是目标服务问题，再给出人话结论和可确认的修复动作。

> 设计目标：不依赖外网 LLM、不依赖 pip 第三方包，小白也能用。

产品形态：
- **本地 macOS App**（SwiftUI）：普通用户主入口。双击 `Netfix.app` 后自动启动本地引擎，不需要打开终端。
- **本地 Web 控制台**：由 App 或本地服务打开，给高级设置、报告、日志、AI 解释和代理配置向导使用；不要直接打开 `gui/web/index.html` 的 `file://` 页面。
- **CLI**：给高级用户、开发调试和自动化脚本保留。
- **MCP / 本地 HTTP API**：供 Kimi、Codex、Minimax 等 Agent 调用，不是普通用户入口。

边界：
- netfix 不卖住宅 IP、不内置节点。你需要先有自己合法获得的代理服务。
- 住宅代理不是只填一个出口 IP。请从代理服务商后台复制 HTTP/SOCKS 连接参数，通常包含 `host`、`port`、`username`、`password`，例如 `socks5h://user:pass@host:port` 或 `host:port:user:pass`。
- 认证 HTTP/HTTPS/SOCKS 上游通过本地 127.0.0.1 桥接应用，认证 SOCKS 通过本地桥接系统应用；密码保存到本机 Keychain，避免写进系统命令参数。真正切全机系统代理前，App 会让用户确认；出问题时可以回滚。
- 云端 AI 解释是可选功能。没有 API Key 时用本地规则解释；配置 API Key 后，发送前会先脱敏。

---

## 为什么做 netfix

日常开发里，海外 AI 服务（Codex、ChatGPT、GitHub Copilot、API）突然连不上，通常不是电脑坏了，而是：

- 代理客户端没启动 / 端口没监听
- 当前节点被墙或抽风
- DNS 缓存污染 / DoH 旁路
- 系统代理被其他软件覆盖
- Wi-Fi 没拿到正确网关

netfix 把这些检查封装成本地 App 里的「一键诊断」：先快速定位根因，再给出“可以自动处理”“需要你确认”“只能手动操作”的下一步。

---

## 普通用户怎么打开

首选入口是 macOS App：

1. 打开 `Netfix-0.2.0.dmg`。
2. 双击 `Netfix.app`，或拖到 Applications 后从 Launchpad 打开。
3. App 会自动启动本地诊断引擎；正常使用不需要终端、Python 命令或手输 `127.0.0.1`。
4. 首次打开看完隐私说明，点「一键诊断」。

当前仓库里的本地候选包位置：

- `gui/macos/.build/Netfix.app`
- `gui/macos/.build/Netfix-0.2.0.dmg`

付费外发还需要 Developer ID 签名、公证、干净机器 QA、法务与 live provider smoke 证据；所以它现在是本机候选包，不是已经可以公开售卖的成品。

### 住宅代理到底复制什么

不要复制浏览器里查到的“当前出口 IP”，那只是结果，不能拿来连接。要去你购买或自建的代理服务后台，复制代理入口参数：

- URL 形式：`socks5h://user:pass@proxy.example.com:1080`
- 冒号形式：`proxy.example.com:1080:user:pass`
- 表格形式：`host,port,username,password`

把这些粘贴到 App 的「设置 → 代理一键配置」，点「预检」，再点「保存并监控」。需要让所有 App 都走这个代理时，再展开高级操作点「应用到系统代理」。

---

## 高级用户 / Agent 命令

```bash
# 最常用：看 Codex / OpenAI / GitHub 是否可达
python3 netfix.py codex

# 输出 JSON，给 Kimi / Minimax / Codex 解析
python3 netfix.py codex --json

# 指定代理再测一次
python3 netfix.py codex --proxy http://127.0.0.1:10808

# OSI 五层通用分诊
python3 netfix.py triage

# 代理核心专项
python3 netfix.py proxy

# 完整体检（所有诊断跑一遍）
python3 netfix.py doctor

# 分项诊断
python3 netfix.py dns example.com
python3 netfix.py wifi
python3 netfix.py ssl github.com
python3 netfix.py connectivity 8.8.8.8:443

# 自动/半自动修复
python3 netfix.py fix --issue flush-dns-cache --dry-run
python3 netfix.py fix --issue flush-dns-cache
python3 netfix.py fix --all --dry-run

# 查看/回滚
python3 netfix.py report --json
python3 netfix.py rollback

# 查看/裁剪/清理本地报告和事件日志
python3 netfix.py logs --json
python3 netfix.py logs --prune --retention-days 7 --json
python3 netfix.py logs --clear --json

# 知识库查询
python3 netfix.py kb --query MTU

# 持续监控（状态变化自动保存 case / 弹通知）
python3 netfix.py watch --interval 60 --notify --save-case

# 持续验证已保存的住宅/自定义代理 Profile
python3 netfix.py proxy-monitor --profile home-us-1 --interval 60 --json

# 自动切换到健康节点（mihomo 用 API；v2rayN 改写配置后需手动重启 GUI）
python3 netfix.py proxy-switch --auto --dry-run
python3 netfix.py proxy-switch --auto --yes

# 启动本地 API + Web 仪表盘
python3 netfix.py server --host 127.0.0.1 --port 8765
# 然后浏览器打开 http://127.0.0.1:8765/
```

---

## 图形界面

### 原生 macOS App（普通用户主入口）

当前仓库已经有本地候选 App：

- `gui/macos/.build/Netfix.app`
- `gui/macos/.build/Netfix-0.2.0.dmg`

双击 `Netfix.app` 后，它会在 Dock/菜单栏出现，并自动启动本地诊断引擎。正常用户不需要打开终端，也不需要手动访问 `127.0.0.1`。

打开后你可以：

- 在首次启动流程里查看隐私说明
- 点「一键诊断」检查 Codex / OpenAI / GitHub / AI 服务连接
- 点「日志」查看最近报告、事件和日志目录
- 在诊断结果里点「问 AI」，让已配置的模型解释脱敏报告
- 在「设置 → AI」配置 DeepSeek、Kimi/Moonshot、MiniMax、Qwen 或自定义 OpenAI-compatible 供应商
- 在「设置 → 代理」粘贴自己合法获得的代理凭据，做预检、验证、保存、监控和导出
- 在 Dashboard 底部点「控制台」打开同一后端的 Web 控制台

### 高级 Web 仪表盘

Web 控制台是 App 的高级辅助界面或开发入口。不要直接打开 `gui/web/index.html` 的 `file://` 页面；那只是静态文件，无法代表产品跑通。

```bash
python3 netfix.py server --host 127.0.0.1 --port 8765
```

打开浏览器访问 `http://127.0.0.1:8765/`，即可看到：

- AI/开发工具连接急诊首页
- 真实日志 / 最近报告 / 事件时间线
- 诊断/修复失败后的恢复面板：重试、复制失败详情、跳转日志/报告
- 下一步操作卡片、预览和需要你做的事
- 国内模型优先的 LLM 解释配置：DeepSeek、Kimi/Moonshot、MiniMax、Qwen、自定义 OpenAI-compatible
- DeepSeek 默认文本解释，Kimi/MiniMax/Qwen 可作为已保存对应 API Key 的国内备用链路；MiniMax/Kimi/Qwen 可作为图片问诊候选但需要显式开启实验入口；Kimi 默认国内入口为 `https://api.moonshot.cn/v1`，MiniMax 默认国内入口为 `https://api.minimaxi.com/v1`；Web/macOS 都可显式启用或关闭云端 AI，并设置每小时云端请求和图片问诊预算；切换 provider 时会使用对应 provider-scoped Keychain account，避免拿 DeepSeek 的 Key 去调用 Kimi/MiniMax/Qwen。
- 住宅代理连接参数解析、预检、候选行一键保存并启动健康监控、更新已保存 Profile、验证、出口身份报告、安全客户端配置包导出、单 Profile 删除与 Keychain 清理、确认式系统应用和回滚；配置包包含 README、通用 URL、shell env、Mihomo/Clash YAML 和 sing-box JSON 命名文件；认证 HTTP/HTTPS/SOCKS 会通过本地桥接应用；桥接状态卡会直接标出运行中、需要恢复系统代理、未启动或检查失败；监控失败会给出可点击的重新输入代理参数、重启监控、换候选、导出客户端配置包等修复建议

### 开发者重新构建 App

需要 Swift 工具链（macOS 命令行工具即可）：

```bash
cd gui/macos
swift build
swift run Netfix
```

构建产物为 `gui/macos/.build/debug/Netfix`。它会在菜单栏显示图标，点击后弹出诊断面板，并自动启动后台 Python 引擎。

打包成 `.app` 并安装到 `/Applications`：

```bash
cd gui/macos
./build_app.sh
# 脚本会提示是否安装到 /Applications，输入 y 即可
```

该脚本会自动把 Python 后端（`netfix.py`、`netfix/`、`rules/`、`bin/`）复制到 App Resources 中，运行 release audit，做本地 ad-hoc 签名。

源码/开发包仍可 fallback 到 `/usr/bin/env python3`。外发候选包应内置 `netfix-backend` 独立后端二进制；当前构建脚本已经支持并验证这一模式。真正付费外发还需要 Developer ID 签名、notarization、clean-machine QA 和发布/更新策略。

如果已经用 PyInstaller/Nuitka 等工具产出独立后端，可在打包时传入：

```bash
NETFIX_BACKEND_BIN=/path/to/netfix-backend ./build_app.sh
```

项目提供了 PyInstaller 构建入口：

```bash
python3 -m venv /tmp/netfix-pyinstaller-venv
/tmp/netfix-pyinstaller-venv/bin/python -m pip install --upgrade pip pyinstaller
PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python ./scripts/build_backend_binary.sh
NETFIX_BACKEND_BIN=dist/netfix-backend ./gui/macos/build_app.sh --release-candidate
```

正式候选包应要求内置 runtime：

```bash
NETFIX_BACKEND_BIN=dist/netfix-backend \
NETFIX_REQUIRE_BUNDLED_RUNTIME=true \
./gui/macos/build_app.sh --release-candidate
```

该模式会从 allowlist 文件构建干净的 App bundle，执行 bundle release audit，并生成本地 DMG 候选包：`gui/macos/.build/Netfix-0.2.0.dmg`。

仓库里若仍有代理 URL、Shadowrocket/Stash 配置、代理二维码、旧 v2rayN 包等敏感产物，workspace audit 会报告风险，但不会进入二进制包。源码/仓库发布前必须使用更严格的门禁：

```bash
./build_app.sh --release-candidate --strict-workspace
```

发布前可以运行本地 release gate，把 Python/Swift/打包/DMG 校验串起来：

```bash
./scripts/release_gate.sh

# 二进制 App 候选：构建并强制内置 netfix-backend。
PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python \
./scripts/release_gate.sh --with-backend-binary

# 单独验证 DMG 里的 App：挂载 DMG、启动内置 backend、检查核心 API。
NETFIX_REQUIRE_BUNDLED_RUNTIME=true \
./scripts/verify_dmg_backend.sh gui/macos/.build/Netfix-0.2.0.dmg

# 生成干净下载导出包：只复制 DMG、首读说明、release manifest、readiness JSON 和 SHA256SUMS；
# 不复制源码工作区、旧代理包或本地 case。若已有人工发布证据，会复制 evidence JSON 和记录文件。
# SHA256SUMS 和 export-manifest 对 evidence/ 下文件使用相对路径，方便按包内路径校验。
python3 scripts/release_export.py --zip --evidence-file gui/macos/.build/release-evidence.json

# 生成人工发布证据模板；只在 clean-machine QA、结构化法务发布审阅、live provider smoke 都真实完成后改为 true。
# clean-machine QA 现在必须覆盖：DMG 挂载、内置后端 smoke、App/Web/日志/Ask AI fallback 渲染、
# 住宅代理 Profile 生命周期（粘贴/保存监控/更新凭据/导出/删除清理自动恢复）、
# 国内 LLM provider 设置（DeepSeek 文本、provider-scoped Keychain、MiniMax/Kimi/Qwen 图片路由文案）、
# release-readiness.json 复核，以及截图无可见密钥/代理密码。
python3 scripts/clean_machine_qa.py template gui/macos/.build/clean-machine-qa.json \
  --manifest gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json \
  --dmg gui/macos/.build/Netfix-0.2.0.dmg
python3 scripts/clean_machine_qa.py status gui/macos/.build/clean-machine-qa.json
python3 scripts/clean_machine_qa.py validate gui/macos/.build/clean-machine-qa.json
python3 scripts/legal_release_review.py template gui/macos/.build/legal-release-review.json \
  --privacy-policy docs/PRIVACY_POLICY_DRAFT.md \
  --eula docs/EULA_DRAFT.md
python3 scripts/legal_release_review.py status gui/macos/.build/legal-release-review.json
python3 scripts/legal_release_review.py validate gui/macos/.build/legal-release-review.json
python3 scripts/provider_smoke_check.py status --record gui/macos/.build/provider-smoke-live.json
python3 scripts/provider_smoke_check.py --live --require-live --json > gui/macos/.build/provider-smoke-live.json
python3 scripts/release_evidence.py template gui/macos/.build/release-evidence.json \
  --clean-machine-qa-record clean-machine-qa.json \
  --legal-review-record legal-release-review.json \
  --live-provider-smoke-record provider-smoke-live.json
python3 scripts/release_evidence.py status gui/macos/.build/release-evidence.json
python3 scripts/release_evidence.py validate gui/macos/.build/release-evidence.json

# 发布就绪总览：汇总 workspace blockers、bundle audit、内置 runtime、Developer ID、公证、DMG 和人工证据；
# blocker/warning 会带 next steps，方便逐项补齐正式外发证据。
# 未签名/未公证、缺少 clean-machine QA/法务/live smoke 证据的本地候选包会被标记为 NOT READY，这是刻意的。
python3 scripts/release_readiness.py --evidence-file gui/macos/.build/release-evidence.json
python3 scripts/release_readiness.py --evidence-file gui/macos/.build/release-evidence.json --json

# 源码/仓库发布必须使用 strict 模式；当前若仍有旧代理包，会被挡住。
./scripts/release_gate.sh --strict-workspace
```

有 Apple Developer ID 和 Notary 配置时，打包脚本会走正式分发路径：

```bash
NETFIX_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
NETFIX_NOTARY_PROFILE="netfix-notary" \
./gui/macos/build_app.sh --release-candidate
```

也可以不用 keychain profile，改用 `NETFIX_NOTARY_APPLE_ID`、`NETFIX_NOTARY_TEAM_ID`、`NETFIX_NOTARY_PASSWORD`。未提供这些环境变量时，脚本只做本机 ad-hoc 签名，并在 `release-manifest.json` 里如实标记未公证。

---

## 架构简述

```
netfix/
├── cli.py            argparse 子命令
├── service_runner.py CLI 包装器（供 API / MCP 复用）
├── api.py            本地 HTTP API + Web 仪表盘
├── mcp_server.py     MCP stdio 服务器
├── services.py       可配置海外服务目录
├── i18n/             中文平民化文案
├── detect.py         平台 / 系统代理 / 运行中的代理核心检测
├── cores/            v2rayN / mihomo / Clash / WireGuard 等适配器
├── codex.py          OpenAI / GitHub / Codex 可达性探针
├── diagnose.py       诊断调度器
├── reasoner.py       本地规则引擎：证据 → 根因 → 修复
├── fix_engine.py     修复执行、备份、journal、rollback
├── safety.py         命令分级
├── redaction.py      报告/LLM/MCP 脱敏
├── settings.py       非敏感本地设置
├── keychain.py       macOS Keychain 密钥存储
├── llm_provider.py   国内优先的 OpenAI-compatible LLM 适配
├── llm_explain.py    可选云端解释 + 本地 fallback
├── residential_proxy.py 住宅代理凭据解析、应用计划和回滚
├── proxy_bridge.py  本地 127.0.0.1 认证代理桥接
├── report.py         Markdown / JSON / 中文报告
├── kb.py             rules/*.json + final.md 知识库查询
└── utils.py          子进程、JSON、ANSI 剥离等工具

gui/
├── macos/            SwiftUI 菜单栏 App（SPM）
└── web/              浏览器仪表盘
```

数据流：

```
环境检测 (detect) → 核心适配 (cores) → 诊断 (diagnose/services)
     ↓                    ↓                    ↓
reasoner 规则匹配 → fixes / manual_steps
     ↓
report 生成 + 持久化 → CLI / Web / 菜单栏 / Agent 消费
```

---

## LLM / Agent 调用方式

### 方式一：MCP（推荐）

netfix 提供 MCP stdio 服务器，Kimi、Codex、Claude、Cursor 等支持 MCP 的 Agent 可直接调用：

```bash
kimi mcp add netfix --transport stdio --command python3 --args /Users/qibaishi/Desktop/网络/netfix/mcp_server.py
```

注册后，你跟 Agent 说「我 ChatGPT 打不开」，Agent 会自动调用 `netfix_codex`，并根据返回的 JSON 给出中文结论。

MCP 也暴露国内 LLM 能力，但仍受本地安全门禁约束：

- `netfix_llm_providers` 返回 DeepSeek、Kimi/Moonshot、MiniMax、Qwen 等预设，以及每个 provider 的 Keychain/API Key 就绪状态、文本解释就绪状态、图片问诊就绪状态。
- `netfix_explain_llm` 使用最新本地报告做脱敏解释，支持 `mode: "explain"` 或 `mode: "image_question"`；图片问诊只接受 inline PNG/JPEG/WebP/GIF `data:image/...`，最多 3 张，且必须传 `upload_confirmed: true`。
- DeepSeek 是默认文本解释主力；截图/图片问诊会按配置走 MiniMax/Kimi/Qwen 等国内多模态候选，不把 DeepSeek 误当成视觉模型。
- `netfix_proxy_parse` 和 `netfix_proxy_import_preview` 可解析单条或批量供应商代理列表，只返回脱敏 URL、候选行和部署决策。
- MCP 不能保存 API Key 或代理密码，不能验证/应用系统代理；密钥仍通过 Web/macOS Settings 或本地 HTTP API 写入 Keychain。

### 方式二：本地 HTTP API

```bash
python3 netfix.py server --host 127.0.0.1 --port 8765
```

Agent 或任意客户端可请求：

```bash
TOKEN="$(cat ~/.netfix/api-token-*.txt | tail -n 1)"
curl -s http://127.0.0.1:8765/run \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"command":["codex"],"timeout":15}'
```

Web 控制台使用本地 server 设置的 HttpOnly SameSite cookie；token 不再注入 HTML。脚本/Agent 直接调用 HTTP API 时，从启动输出的 `token_file` 读取 token：

```bash
# server 启动行形如：
# netfix API listening on http://127.0.0.1:8765 token_file=/Users/you/.netfix/api-token-12345.txt
TOKEN="$(cat /Users/you/.netfix/api-token-12345.txt)"
curl -s http://127.0.0.1:8765/proxy/parse \
  -H "Content-Type: application/json" \
  -H "Origin: http://127.0.0.1:8765" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"proxy.example.com:8000"}'
```

LLM / 住宅代理产品接口：

产品默认采用国内模型优先策略：DeepSeek 作为低成本、大吞吐的文本解释默认优先项；Kimi/Moonshot、MiniMax、Qwen 作为可配置兜底，其中图片问诊只走声明支持 `image_url` 的国内多模态供应商。DeepSeek 当前只按文本能力使用，不能把“用户发图片问网络问题”误标成 DeepSeek 已支持。国内 provider preset 记录官方文档来源和最近核验日期；MiniMax-M3 按当前 OpenAI-compatible 文档使用 `max_completion_tokens`，避免继续依赖旧的 `max_tokens` 字段。

```bash
# 查看国内优先模型预设和每个供应商的本地 Keychain 就绪状态
curl -s http://127.0.0.1:8765/llm/providers \
  -H "X-Netfix-Token: $TOKEN"

# 保存 LLM 配置并启用云端解释；api_key 会写入 macOS Keychain，不写进 settings.json
export DEEPSEEK_API_KEY="sk-..."
cat <<JSON | curl -s http://127.0.0.1:8765/settings/llm \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d @-
{"enabled":true,"provider":"deepseek","base_url":"https://api.deepseek.com","model":"deepseek-v4-flash","api_key_account":"deepseek","api_key":"$DEEPSEEK_API_KEY","redaction_level":"balanced","upload_consent":"ask_each_time","fallback":{"enabled":true,"domestic_only":true,"include_custom":false,"include_global":false,"chain":["deepseek","moonshot_kimi","minimax","qwen"],"vision_chain":["minimax","moonshot_kimi","qwen"]},"budget":{"enabled":true,"persist_usage_ledger":true,"max_requests_per_hour":60,"max_image_requests_per_hour":12,"cooldown_seconds_after_rate_limit":300,"cooldown_seconds_after_quota":3600},"features":{"explain":true,"repair_steps":true,"residential_proxy_guide":true,"image_question":false}}
JSON

# 如果本机已有 DeepSeek 侧车配置，也可以显式导入；不会打印 API Key。
curl -s http://127.0.0.1:8765/llm/import-deepseek-sidecar-key \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"confirmation":"IMPORT_DEEPSEEK_SIDECAR_KEY","api_key_account":"deepseek","enable_llm":true}'

# 临时测试也可以不用 Keychain，改用 provider-scoped env key：
# NETFIX_LLM_API_KEY_DEEPSEEK=sk-... python3 netfix.py server --host 127.0.0.1 --port 8765

# 离线 fixture smoke：验证 DeepSeek 文本响应、Kimi/MiniMax/Qwen 图片问诊响应解析和 usage 摘要。
python3 scripts/provider_smoke_check.py --json

# 发布前文案门禁：禁止“干净住宅 IP / 绕过风控”类承诺，也禁止把 DeepSeek 误宣成图片/多模态模型。
python3 scripts/marketing_claims_check.py --json

# 可选 live smoke：有 provider-scoped Keychain/env key 时才会真实调用供应商；缺 key 默认跳过。
NETFIX_LLM_API_KEY_DEEPSEEK=sk-... \
python3 scripts/provider_smoke_check.py --live --provider deepseek --json

# 付费外发证据必须是 live + require-live，全量覆盖当前营销的国内供应商；fixture/skipped 结果不能解锁 release_ready。
python3 scripts/provider_smoke_check.py --live --require-live --json > gui/macos/.build/provider-smoke-live.json

# 对最新报告做脱敏后解释；必须确认本次上传，否则会回退本地规则
curl -s http://127.0.0.1:8765/explain_llm \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"question":"请解释根因和下一步","redaction_level":"balanced","upload_confirmed":true}'

# 查看/保存本地隐私设置；日志保留默认 7 天
curl -s http://127.0.0.1:8765/settings/privacy \
  -H "X-Netfix-Token: $TOKEN"
curl -s http://127.0.0.1:8765/settings/privacy \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"log_retention_enabled":true,"log_retention_days":7,"save_latest_report":true,"persist_proxy_identity_report":false}'

# 清理本地最近报告和事件日志，不删除 settings 或 Keychain
curl -s http://127.0.0.1:8765/logs/clear \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"latest_report":true,"events":true}'

# 删除 Netfix 本地报告、事件、settings 和已知 Keychain 项；不会删除 App 或系统网络配置
curl -s http://127.0.0.1:8765/data/clear \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"confirm":"DELETE_NETFIX_LOCAL_DATA","keychain":true}'

# 解析单条住宅代理凭据，返回 redacted_url 和 deployment_decision，不保存密码
curl -s http://127.0.0.1:8765/proxy/parse \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"http://user:pass@proxy.example.com:8000"}'

# 批量预检供应商粘贴列表；支持 URL、host:port:user:pass、host,port,user,password 等常见行。
# 只返回脱敏 URL、候选行和部署决策，不保存密码，不写 Keychain；Web/macOS 可对候选行一键保存并按设置启动监控。
curl -s http://127.0.0.1:8765/proxy/import-preview \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"host,port,user,password\nproxy.example.com,8000,user,pass\nhttp://user:pass@proxy2.example.com:9000"}'

# 验证住宅代理连通性；include_identity 会额外返回出口 IP、地理/ASN、IP 类型、DNS/IPv6 风险和目标矩阵
curl -s http://127.0.0.1:8765/proxy/validate \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"http://user:pass@proxy.example.com:8000","timeout":10,"include_identity":true}'

# 保存后的 profile 可持续验证；结果会写入 profile.last_check。
# 默认只保存低细节 last_identity_summary；只有开启 persist_proxy_identity_report 才保存完整 last_identity_report。
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/validate \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"timeout":10,"include_identity":true}'

# 保存代理 Profile 时也可以同时启动本地后台健康监控；这不会修改系统代理。
curl -s http://127.0.0.1:8765/proxy/profiles \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"http://user:pass@proxy.example.com:8000","start_monitor":true,"monitor_interval":60,"timeout":10,"target_profile":"ai_dev"}'

# 更新/轮换已保存 Profile 的 host、端口、用户名或密码；保留 Profile ID，同一个 Keychain 账户写入新密码，可按当前矩阵重启监控；不会修改系统代理。
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/replace \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"input":"http://new-user:new-pass@new.proxy.example.com:9000","start_monitor":true,"monitor_interval":60,"timeout":10,"target_profile":"ai_dev"}'

# 删除单个 Profile；会移除本地配置并尝试删除对应 Keychain 密码。如果该 Profile 正在被后台监控，或被保存为重启自动恢复监控目标，会停止/清理对应监控；不会修改系统代理。
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/delete \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{}'

# 导出安全客户端配置包；package 包含 README.md 和 URL/env/Mihomo/Clash/sing-box 命名文件。
# 兼容字段 snippets 仍保留；不会返回 Keychain 密码，认证配置使用 <password> 占位符。
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/export \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"format":"all"}'

# 启动/查看/停止本地后台健康监控；启动配置会保存到 settings，Netfix 后端重启后会自动恢复
curl -s http://127.0.0.1:8765/proxy/monitor/start \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"profile_id":"<id>","interval":60,"timeout":10}'
curl -s http://127.0.0.1:8765/proxy/monitor \
  -H "X-Netfix-Token: $TOKEN"
curl -s http://127.0.0.1:8765/proxy/monitor/stop \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{}'

# 预览应用计划；响应包含 deployment_decision。system 模式会修改系统网络设置，正式应用必须带确认短语
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/apply-dry-run \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"mode":"system"}'

# 确认应用到 macOS 系统代理；认证 HTTP/HTTPS/SOCKS 上游会通过 127.0.0.1 本地桥接应用，桥接期间需要保持 Netfix 运行
curl -s http://127.0.0.1:8765/proxy/profiles/<id>/apply \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"mode":"system","confirmed":true,"confirmation":"APPLY_PROXY_PROFILE","verify":true,"rollback_on_verify_failure":true}'

# 查看当前本地桥接状态；响应包含 lifecycle、startup_check、请求计数、活跃连接、最近本机客户端和 stale_check。
# 桥接审计不记录目标 URL 或路径；127.0.0.1 端口仍可能被本机其它进程使用。
curl -s http://127.0.0.1:8765/proxy/bridge \
  -H "X-Netfix-Token: $TOKEN"

# 显式开启启动时桥接自动恢复；只会尝试重启本地 127.0.0.1 桥接，不会静默改写系统代理
curl -s http://127.0.0.1:8765/settings/proxy-bridge \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"auto_restart_enabled":true,"idle_timeout":0}'

# 恢复失效桥接：只写回应由 Netfix 应用前备份的系统代理状态
curl -s http://127.0.0.1:8765/proxy/bridge/recover \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"confirmed":true,"confirmation":"RESTORE_STALE_PROXY_BRIDGE"}'

# 回滚上次由 Netfix 应用前备份的系统代理状态
curl -s http://127.0.0.1:8765/proxy/profiles/rollback \
  -H "Content-Type: application/json" \
  -H "X-Netfix-Token: $TOKEN" \
  -d '{"confirmed":true,"confirmation":"ROLLBACK_PROXY_PROFILE"}'
```

### 方式三：CLI + --json

所有命令支持 `--json`。LLM 读 stdout 并 `json.loads()` 解析即可。

```bash
python3 netfix.py codex --json
```

关键字段：

```json
{
  "meta": { "version", "timestamp", "platform", "hostname" },
  "environment": {
    "gui_client", "active_core", "mixed_port", "system_proxy",
    "active_profile", "profiles"
  },
  "diagnostics": [
    { "name", "status", "duration_ms", "details" }
  ],
  "root_causes": [
    { "id", "description", "confidence", "anchor" }
  ],
  "fixes": [
    { "id", "tier", "description", "command", "verify", "auto" }
  ],
  "manual_steps": [
    { "id", "description", "steps" }
  ]
}
```

建议 LLM 工作流：

1. `python3 netfix.py codex --json`
2. 读 `root_causes` 和 `fixes`
3. 低风险项可以直接执行；会改系统设置的项必须先问用户；只能手动处理的项只给清单
4. 用户确认修好后，提议把 case 沉淀到 `cases/`

---

## 安全说明

后端 JSON 里保留 `tier` 作为内部安全等级字段，但普通界面不展示这个词。

| 安全等级 | 类型 | 默认行为 |
|------|------|---------|
| 0 | 只读诊断 | 自动执行 |
| 1 | 低风险修复（如刷新 DNS 缓存） | 自动执行，`--dry-run` 可预览 |
| 2 | 变更型修复（改配置、切节点） | 先备份 → 出 diff → 用户确认；`--yes` 只对低风险修复生效 |
| 3 | 仅手动清单 | 不执行，只输出精确步骤 |

- 所有会改配置的修改都会先备份原文件，并写入 `~/.netfix/journal.jsonl`。
- `rollback` 可以撤销最近一次带备份的修改。
- netfix 本身不请求 root，但部分修复命令会调用 `sudo`（如刷新 DNS 缓存），执行前会提示。

---

## 贡献 / case 沉淀

遇到真实故障并修好后，欢迎把过程写到 `cases/YYYY-MM-DD-症状关键词.md`，格式参考：

```markdown
# 2026-06-17 - Codex API timeout

- 症状：...
- netfix 输出关键字段：...
- 根因：...
- 修复：...
- 验证：...
```

这些 case 会逐步反哺 `rules/symptoms.json` 和 `final.md`，让 netfix 越用越准。

---

## License

MIT
