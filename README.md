# Netfix

[English README](README.en.md)

![Netfix — 粘贴代理，让 Mac 正确使用已有的代理](assets/github/hero.zh.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macos-blue)
![privacy: 本地优先](https://img.shields.io/badge/privacy-%E6%9C%AC%E5%9C%B0%E4%BC%98%E5%85%88-0f766e)

> **买了代理不会配 Mac？把服务商后台那串参数粘贴进来，Netfix 帮你调好。**

Netfix 是 macOS 上的一款小工具：把你从代理服务商买来的连接参数贴进来，它会先测试能不能用，再保存到 Mac 钥匙串，最后由你确认是否开始使用代理。改之前自动备份，不用时一键恢复。

**不接 API Key 也能用。** 诊断、规则解释、代理预检、保存、部署、恢复都在本地完成。需要时再接 DeepSeek / Kimi / MiniMax / Qwen 或任何 OpenAI-compatible 服务，云端模型只负责把**已脱敏的诊断报告**解释成人话。

---

## 三步把已有代理部署到这台 Mac

1. **下载 App**：双击 DMG，把 Netfix 拖进「应用程序」。第一次打开如果提示“无法验证开发者”，到「系统设置 → 隐私与安全性 → 仍要打开」。
2. **粘贴参数**：打开 Netfix，在主界面点「粘贴代理参数」，把服务商后台那一行连接参数粘进去。Netfix 会先检查能不能用，再保存到本机密码库。
3. **开始使用**：检查通过后点「开始使用代理」。Netfix 会先备份当前网络设置，再启用代理；不用时打开设置，点「恢复原来的网络设置」一键恢复。

支持的连接参数格式：

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

这些参数通常在服务商后台的「个人中心」「节点列表」或「连接信息」里，找 HTTP 或 SOCKS5 的那一行复制即可。

不支持 ss://、vmess:// 或 Clash/sing-box 订阅链接 —— 请回服务商后台复制 HTTP 或 SOCKS5 的参数。

主界面会用一个绿色 / 蓝色 / 橙色 / 红色卡片告诉你 **现在到底发生了什么**：

* 蓝色「还没有粘贴代理参数」→ 去粘贴。
* 绿色「正在使用代理上网」→ 一切正常。
* 橙色「代理还在用，但刚才一次检测没通过」→ 点一键诊断看具体项。
* 红色「系统网络需要恢复」→ 点「恢复原来的网络设置」。
* 出错时不再显示工程日志，只说人话并告诉你下一步点什么；想看原始日志可以点「查看日志」。

![Netfix 用户路径](assets/github/workflow.zh.png)

有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发；密码进入 macOS Keychain，不写进 shell 历史、日志或发布包。

---

## 当前版本说明

当前版本 **v0.2.0-qa.1 预览版**可以帮你粘贴参数、预检、部署、恢复网络。它还没有完成 Apple Developer ID 签名和公证，首次打开时 macOS 可能会提示“无法验证开发者”。请在 **系统设置 → 隐私与安全性** 里点击 **仍要打开**。现在适合技术测试用户试用；正式面向普通用户还需要签名和公证。

你需要准备的是代理服务后台里的 **HTTP/SOCKS5 连接参数**，例如 `host:port:用户名:密码`。不要复制“当前出口 IP”；它只是检测结果，不能拿来连接。Netfix 不是 Clash 客户端，不解析订阅；`ss://`、`vmess://`、Clash/sing-box 订阅链接暂不支持，请到服务商后台找 host、port、用户名、密码。

系统要求：macOS 13 或更新版本；Apple Silicon / Intel Mac 都可试；修改系统代理时 macOS 可能会要求输入本机密码。

```bash
# 先看脚本会做什么，不安装、不改配置
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --dry-run

# 技术测试用户安装 Netfix.app（QA 版本，未签名）
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

# 卸载本机 App
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --uninstall
```

安装脚本会把 App 放到 `~/Applications/Netfix.app`，打开 App。如果你只想看源码或不想用 App，可以从源码运行。

---

## 它解决什么问题

| 场景 | 人话描述 |
|------|---------|
| **买了代理不会配 Mac** | 粘贴连接参数 → 预检 → 保存到 Keychain → 一键部署 |
| **手机能用，Mac 不会用** | 检测 Mac 的系统代理、DNS、IPv6、运行中的代理软件状态 |
| **Codex / ChatGPT / GitHub 连不上** | 定位是网络层、代理层、认证层还是目标服务端的问题 |
| **代理开了但某些软件不走** | 看当前系统代理是否生效，哪些 App 可能不走系统代理 |
| **终端能连，App 不能连** | 对比终端环境变量和系统代理设置 |
| **换电脑后想恢复配置** | 代理参数保存在 Keychain，导出/迁移时有脱敏保护 |

---

## 跟现有工具比

| 工具 | 它做什么 | Netfix 多做的事 |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | 客户端代理 App：你提供节点，它们转发流量 | Netfix 告诉你**这台 Mac 现在的网络到底能不能让代理连上**，应用前预检，失败可恢复 |
| **Activity Monitor / `netstat`** | 通用进程/端口检查 | 一份报告同时覆盖 DNS / 系统代理 / 代理软件 / IPv6 / TLS / 目标服务，告诉你"坏在哪一层" |
| **聊天机器人手写 `curl` / `ping`** | 模型临时拼命令 | 结构化 JSON 输出、分级修复、自动备份原网络、发云端前先脱敏 |
| **网络监控小部件** | 看实时速率/信号 | 修复向：粘贴参数 → 预检 → 部署 → 监控 → 恢复，一条龙 |

---

## 它不做什么

- **不卖代理，不内置节点，不承诺第三方服务质量。** Netfix 只帮你解析、预检、保存、部署、监控、恢复你自己已有的连接参数。
- **严格遵守第三方平台的账号、风险、地理与滥用规则。**
- **不会**把你的代理密码、API Key、原始报告、二维码、cookie 自动泄露到云端、shell 历史、截图或 GitHub Issue。

---

## 如果失败，我怎么恢复

Netfix 在改系统代理之前会自动备份你原来的网络设置。

- **App 里恢复**：打开 Netfix 设置，在代理区域点「恢复原来的网络设置」。
- **命令恢复**：如果你会用终端，可以运行 `python3 netfix.py rollback`。
- **仍然不行**：重启 Mac，系统代理设置会回到默认状态；然后检查服务商后台的参数是否复制完整。

---

## AI 解释怎么接（可选）

不接 API 也能用。Netfix 默认用本地规则解释诊断结果。接 API 以后，云端模型只负责把脱敏报告解释成人话。

### App 路径

打开「设置 → AI」，选择 DeepSeek、Kimi/Moonshot、MiniMax、Qwen 或自定义 OpenAI-compatible 供应商，贴 API Key，保存。Key 进入 Keychain。

建议新手直接选：

- **DeepSeek**：国内访问稳定，文本解释主力
- **Kimi / Moonshot**：长文本 + 图片问诊
- **MiniMax**：图片问诊备选
- **自定义**：任何 OpenAI-compatible 服务，填写 `base_url` + `model` + `api_key`

### 环境变量路径

```bash
export NETFIX_LLM_API_KEY_DEEPSEEK="sk-..."
python3 netfix.py explain --provider deepseek --json
```

### 本地 API 配置示例

```bash
curl -s http://127.0.0.1:8765/llm/providers \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"api_key":"$DEEPSEEK_API_KEY","fallback":{"enabled":true,"chain":["deepseek","moonshot_kimi","minimax","qwen"],"vision_chain":["minimax","moonshot_kimi","qwen"],"persist_usage_ledger":true}}'
```

图片问诊必须用户确认上传：

```bash
curl -s http://127.0.0.1:8765/llm/explain \
  -H "Content-Type: application/json" \
  -d '{"mode":"image_question","upload_confirmed":true,"image":"data:image/..."}'
```

MCP 工具名：

- `netfix_llm_providers`
- `netfix_explain_llm`

给 Agent 的参数写法里会出现 `mode: "image_question"`、`upload_confirmed: true` 和 `data:image/...`。DeepSeek 是默认文本解释主力；图片路径走 MiniMax、Kimi/Moonshot 或 Qwen，不能把 DeepSeek 说成图片/视觉模型。MCP 不能保存 API Key 或代理密码，只调用本地 Netfix 服务。

---

## 开发者与 Agent 入口

如果你用 Codex / Kimi / Claude / Cursor / MiniMax-compatible 本地智能体，可以把 Netfix 注册为 MCP 工具。普通用户不需要看这一节。

已经安装 App 的用户不用找仓库脚本：

1. 打开 Netfix。
2. 进入「设置 → AI 编程助手 → 复制给 Codex」，把命令粘到 Codex 终端里，重启 Codex。
3. 如果你用 Kimi，点「复制 Kimi/通用配置」。当前部分 Kimi Code CLI 版本没有 `mcp add` 命令，不要粘贴旧命令；把通用 stdio 配置填到支持 MCP 的 Kimi/Agent 宿主里。
4. Claude Desktop：把配置粘到 `~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers` 段。
5. Cursor：把配置粘到 `~/.cursor/mcp.json` 或项目根目录 `.cursor/mcp.json` 的 `mcpServers` 段。
6. MiniMax 或其他本地智能体：只要宿主支持 MCP stdio，就填 `command: python3` 和脚本打印的 `args`。Netfix 不假设 MiniMax 一定有官方 MCP client。

源码用户可以从仓库根目录注册 Codex：

```bash
./scripts/install_mcp.sh --all
./scripts/install_mcp.sh --all --dry-run
```

Codex 手动注册示例：

```bash
codex mcp add netfix -- python3 "$(pwd)/netfix/mcp_server.py"
codex mcp list
```

Kimi/Claude/Cursor/MiniMax-compatible 通用 MCP stdio 配置：

```yaml
name: netfix
command: python3
args:
  - /Users/you/Applications/Netfix.app/Contents/Resources/netfix/mcp_server.py
```

Agent 端标准入口：

```bash
python3 netfix.py codex --json
```

重点读 `environment.active_profile`、`diagnostics`、`root_causes`、`fixes` 和 `manual_steps`。低风险修复可以执行；会改系统配置的动作必须先让用户确认；只能手动处理的动作只给清单。

### 从源码直接试

```bash
pip install -e .
python3 netfix.py codex
python3 netfix.py codex --json
python3 netfix.py server --host 127.0.0.1 --port 8765
```

第三条命令会启动本地 Web 控制台，浏览器打开 `http://127.0.0.1:8765/`。不要直接双击 `gui/web/index.html`，`file://` 页面没有服务，不能代表产品跑通。

构建本地 macOS App：

```bash
cd gui/macos
swift build
./build_app.sh
open .build/Netfix.app
```

正式给普通用户的目标形态是 `Netfix.app`：双击打开，自动启动本地诊断引擎，不需要终端。

---

## 真实 case 速览

`cases/` 目录里都是脱敏后的真实场景，入口见 [Case Index](cases/INDEX.md)。最适合第一次了解 Netfix 的故事是：[普通用户第一次部署代理的 9 个坑](cases/2026-06-29-普通用户代理部署体验审查.md)。它解释了为什么 Netfix 把流程做成“粘贴参数 → 预检 → 部署 → 恢复”，而不是让用户自己猜系统代理、IPv6、出口 IP 和密码保存位置。

另外几条有代表性的 case：

- **[Codex 报连不上，其实是 API Key 失效](cases/20260617-1405-codex-reachable-needs-key.md)**：网络层一切正常，Netfix 会指出根因不在你这边。
- **[健康快照](cases/2026-06-17-healthy-baseline.md)**：问题解决前后做对照，作为以后同类故障的快速比对模板。

新 case 欢迎按 `cases/TEMPLATE.md` 提交，PR 前请读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

---

## FAQ

**不接 API Key 能用吗？**

能。诊断、规则解释、代理预检、保存、开始使用和恢复网络都在本地完成。API Key 只用于你主动开启云端 AI 解释时。

| 功能 | 不接 API Key | 接 API Key 后 |
|------|-------------|--------------|
| 网络诊断 | ✅ 本地规则解释 | ✅ 本地 + 云端人话解释 |
| 代理预检/部署 | ✅ 可用 | ✅ 可用 |
| AI 详细解释 | ⚠️ 本地模板 | ✅ 模型基于脱敏报告生成 |
| 图片问诊 | ❌ 不可用 | ✅ 需确认后上传 |

**会不会改坏我的网络？**

正式改系统代理前会备份原网络设置。不用时点「恢复原来的网络设置」即可还原。你也可以在终端运行 `python3 netfix.py rollback`。

**我的代理密码和 API Key 存在哪里？**

只写入 macOS Keychain，不进日志、报告、截图、发布包或 GitHub Issue。

**支持哪些代理格式？**

支持 `host:port:user:pass`、`http://user:pass@host:port`、`socks5://user:pass@host:port`、`host,port,user,pass`。暂不支持 `ss://`、`vmess://` 或 Clash/sing-box 订阅链接。

---

## 功能概览

| 能力 | 普通用户看到什么 | 开发者接口 |
|---|---|---|
| 一键诊断 | 哪一层坏了，下一步点什么 | `python3 netfix.py codex --json` |
| 代理粘贴部署 | 粘贴参数、预检、保存、部署、恢复 | `proxy`, `proxy-monitor`, `proxy-switch` |
| AI 解释 | 可选云端解释，先脱敏再发送 | 本地 HTTP API / MCP |
| 健康维护 | 节点异常、IPv6/TLS/DNS 问题提示 | `watch`, `report`, `logs` |
| Agent 接入 | Codex / Kimi / Claude / Cursor 可复制注册命令 | `netfix/mcp_server.py` |
| 安全恢复 | 改系统代理前备份，失败可恢复 | `fix`, `rollback`, journal |

---

## 安全边界

- 本地优先：诊断和规则推断不依赖外网 LLM。
- 低风险修复可直接执行；会改系统配置的修复必须用户确认。
- 代理密码和 API Key 不进报告、截图、日志、导出包或 GitHub Issue。
- 图片问诊不会自动识别图片像素里的可见密码，上传前用户必须自己确认已脱敏。
- Netfix 不提供代理服务，不承诺第三方服务质量，不帮助绕过第三方账号、风险控制或滥用控制。

---

## 开源发布状态

源码开源路径已经有门禁：`scripts/source_export.py` 会生成干净源码快照，排除旧代理资料、DMG/ZIP、build 输出和本机运行态。公开发布建议发布 `open-source-export/Netfix-0.2.0-source`，不要直接把开发工作区当发布包。

验证命令：

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke
python3 scripts/release_preflight.py --with-dmg-smoke --json
python3 scripts/release_preflight.py --with-dmg-smoke \
  --write-record gui/macos/.build/release-export/Netfix-0.2.0-macos/download-qa-preflight.json
(cd gui/macos/.build/release-export/Netfix-0.2.0-macos && python3 verify-download.py --require-recorded-preflight)
```

如果 `release_audit` 报 `tracked-release-artifact`，说明发布包曾进过 git 索引。只从索引移除，不删本地文件：

```bash
git ls-files 'Netfix-*.dmg' 'Netfix-*.zip'
git rm --cached Netfix-0.2.0.dmg Netfix-0.2.0-macos.zip
python3 scripts/release_audit.py --scope workspace --root .
```

二进制外发需要另过一组门禁：Developer ID 签名、公证、干净机器 QA、法务草案确认、live provider smoke。没完成前只能叫本地候选包，不能叫正式外发版。

---

## 仓库导览

```text
netfix/
├── netfix.py              命令行入口
├── netfix/                诊断、推理、修复、API、MCP
├── gui/macos/             SwiftUI 本地 App
├── gui/web/               本地 Web 控制台
├── rules/                 服务、症状、根因规则
├── scripts/               发布、审计、MCP 注册脚本
├── tests/                 Python / API / MCP / UI 文本测试
├── assets/github/         GitHub 中英双语视觉资产
└── docs/github/           GitHub 发布、截图、运营说明
```

---

如果 Netfix 帮你定位过一次 Mac 网络问题，欢迎点右上角 Star。这样你能看到签名版、截图/GIF 和新 case 的后续进展。

---

## 贡献

欢迎提交：

- 新的脱敏 case，放到 `cases/YYYY-MM-DD-症状关键词.md`。
- 新的症状规则，改 `rules/symptoms.json`。
- 新的服务分组，改 `rules/services.json`。
- 新的代理软件适配器，放到 `netfix/cores/`。
- 更清楚的界面文案、截图和安装说明。

提交前请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。GitHub Issue 里不要贴真实代理密码、API Key、二维码、cookie、bearer token 或原始报告。

---

## License

MIT
