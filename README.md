# Netfix

[English README](README.en.md)

![Netfix — 粘贴代理，让 Mac 正确使用已有代理](assets/github/hero.zh.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: 本地优先](https://img.shields.io/badge/privacy-%E6%9C%AC%E5%9C%B0%E4%BC%98%E5%85%88-0f766e)
![agent: MCP 就绪](https://img.shields.io/badge/agent-MCP%20ready-111827)

> **买了代理不会配？粘贴一行，让 Mac 正确使用你已有的代理。**

Netfix 是 macOS 上的本地网络诊断与配置助手：把你从代理服务商后台复制来的连接信息贴进来，它会先检测能不能用，再保存到本机密码库，最后由你确认是否让这台 Mac 开始使用。改之前自动备份，不用时一键回滚。

**不接 API Key 也能用。** 诊断、规则解释、代理预检、保存、部署、恢复都在本地完成。需要时再接 DeepSeek / Kimi / MiniMax / Qwen 或任何 OpenAI-compatible 服务，云端模型只负责把**已脱敏的诊断报告**解释成人话。

---

## ⚠️ 当前版本说明

这是 **v0.2.0-qa.1 预览版**，DMG 还没有完成 Apple Developer ID 签名和公证。首次打开时，macOS 可能会提示“无法验证开发者”。请在 **系统设置 → 隐私与安全性** 里点击 **仍要打开**。现在适合技术测试用户试用；正式面向普通用户还需要 Developer ID 签名和公证。

你需要准备的是代理服务后台里的 **HTTP/SOCKS5 连接参数**，例如 `host:port:用户名:密码`。不要复制“当前出口 IP”；它只是检测结果，不能拿来连接。Netfix 不是 Clash 客户端，不解析订阅；`ss://`、`vmess://`、Clash/sing-box 订阅链接暂不支持，请到服务商后台找 host、port、用户名、密码。

系统要求：macOS 13 或更新版本；Apple Silicon / Intel Mac 都可试；修改系统代理时 macOS 可能会要求输入本机密码；可选 MCP 接入需要本机有 `python3`。

```bash
# 先看脚本会做什么，不安装、不改配置
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --dry-run

# 技术测试用户安装 Netfix.app（QA 版本，未签名）
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

# 卸载本机 App 和 Codex MCP 注册
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --uninstall
```

安装脚本会把 App 放到 `~/Applications/Netfix.app`，打开 App，并在本机有 Codex CLI 时注册 MCP。脚本最后还会打印 Kimi / Claude Desktop / Cursor / MiniMax-compatible 本地智能体可复制的 MCP stdio 配置。如果你只想看源码或不想用 App：

```bash
pip install -e .
python3 netfix.py codex --json
```

---

## 三步把已有代理部署到 Mac

1. **复制**：去你的代理服务后台，复制一整行 HTTP/SOCKS5 连接参数。
2. **粘贴**：在 Netfix 里粘贴，点「检查并保存到这台 Mac」。
3. **确认**：检查通过后，点「开始使用这台 Mac 上网」。Netfix 会先备份当前网络设置，再应用代理。

![Netfix 用户路径](assets/github/workflow.zh.png)

---

## 它解决什么问题

| 场景 | 人话描述 |
|------|---------|
| **买了代理不会配 Mac** | 粘贴连接参数 → 预检 → 保存到 Keychain → 一键部署 |
| **手机能用，Mac 不会用** | 检测 Mac 的系统代理、DNS、IPv6、运行中的代理核心状态 |
| **Codex / ChatGPT / GitHub 连不上** | 定位是网络层、代理层、认证层还是目标服务端的问题 |
| **代理开了但某些软件不走** | 看当前系统代理是否生效，哪些 App 可能绕过 |
| **终端能连，App 不能连** | 对比终端环境变量和系统代理设置 |
| **换电脑后想恢复配置** | 代理参数保存在 Keychain，导出/迁移时有脱敏保护 |

---

## 跟现有工具比

| 工具 | 它做什么 | Netfix 多做的事 |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | 客户端代理 App：你提供节点，它们转发流量 | Netfix 告诉你**这台 Mac 现在的网络到底能不能让代理连上**，应用前预检，失败可回滚 |
| **Activity Monitor / `netstat`** | 通用进程/端口检查 | 一份报告同时覆盖 DNS / 系统代理 / 代理核心 / IPv6 / TLS / 目标服务，告诉你"坏在哪一层" |
| **聊天机器人手写 `curl` / `ping`** | 模型临时拼命令 | 结构化 JSON 输出、分级修复、自动备份原网络、发云端前先脱敏 |
| **网络监控小部件** | 看实时速率/信号 | 修复向：粘贴参数 → 预检 → 部署 → 监控 → 还原，一条龙 |

---

## 它不做什么

- **不卖代理，不内置节点，不承诺第三方服务质量。** Netfix 只帮你解析、预检、保存、部署、监控、恢复你自己已有的连接参数。
- **严格遵守第三方平台的账号、风险控制、地理与滥用规则；不做任何形式的规避。**
- **不会**把你的代理密码、API Key、原始报告、二维码、cookie 自动泄露到云端、shell 历史、截图或 GitHub Issue。

---

## 接进 Codex / Kimi / Claude / Cursor / MiniMax-compatible 本地智能体

已经安装 App 的用户不用找仓库脚本：

1. 打开 Netfix。
2. 进入「设置 → AI 编程助手 → 复制给 Codex」，把命令粘到 Codex 终端里，重启 Codex。
3. 如果你用 Kimi，点「复制 Kimi/通用配置」。当前部分 Kimi Code CLI 版本没有 `mcp add` 命令，不要粘贴旧命令；把通用 stdio 配置填到支持 MCP 的 Kimi/Agent 宿主里。
4. Claude Desktop：把配置粘到 `~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers` 段。
5. Cursor：把配置粘到 `~/.cursor/mcp.json` 或项目根目录 `.cursor/mcp.json` 的 `mcpServers` 段。
6. MiniMax 或其他本地智能体：只要宿主支持 MCP stdio，就填 `command: python3` 和脚本打印的 `args`。Netfix 不假设 MiniMax 一定有官方 MCP client。

源码用户可以从仓库根目录注册 Codex，并对 Kimi 做能力检测：

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

---

## 当前能怎么用

当前仓库优先保证源码开源、可审计、可本地运行。公开签名 `.dmg` 还没有完成 Developer ID 签名和公证，所以不要把本地候选包宣传成正式下载版。

### 技术测试用户：装 QA App

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash
```

这条命令会下载 DMG、校验 SHA256、安装 `Netfix.app` 到 `~/Applications`、打开 App、烟测 App 内置 MCP；如果本机有 Codex CLI，会注册 Netfix MCP；如果是 Kimi / Claude / Cursor / MiniMax-compatible 本地智能体，脚本会打印可复制的 stdio 配置。当前 QA DMG 还没有 Developer ID 签名和公证，所以现在能做到"技术测试用户一行安装"，还不能包装成"普通小白稳定可用的正式安装命令"。

安装后如果找不到 App：它放在你的用户应用程序文件夹 `~/Applications/Netfix.app`，可以按 `⌘ + 空格` 搜索 `Netfix` 打开。

卸载：

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --uninstall
```

### 从源码直接试

```bash
python3 netfix.py codex
python3 netfix.py codex --json
python3 netfix.py server --host 127.0.0.1 --port 8765
```

第三条命令会启动本地 Web 控制台，浏览器打开 `http://127.0.0.1:8765/`。不要直接双击 `gui/web/index.html`，`file://` 页面没有后端，不能代表产品跑通。

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

`cases/` 目录里都是脱敏后的真实场景，入口见 [Case Index](cases/INDEX.md)。最适合第一次了解 Netfix 的故事是：[普通用户第一次部署代理的 9 个坑](cases/2026-06-29-普通用户代理部署体验审查.md)。它解释了为什么 Netfix 把流程做成“粘贴参数 → 预检 → 部署 → 回滚”，而不是让用户自己猜系统代理、IPv6、出口 IP 和密码保存位置。

另外几条有代表性的 case：

- **[Codex 报连不上，其实是 API Key 失效](cases/20260617-1405-codex-reachable-needs-key.md)**：网络层一切正常，Netfix 会指出根因不在你这边。
- **[健康基线快照](cases/2026-06-17-healthy-baseline.md)**：问题解决前后做对照，作为以后同类故障的快速比对模板。

新 case 欢迎按 `cases/TEMPLATE.md` 提交，PR 前请读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

---

## 代理到底复制什么

不要复制"当前出口 IP"。出口 IP 只是检测结果，不能拿来连接。

请从你自己合法获得的代理服务后台复制连接参数。Netfix 支持常见写法：

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

在 App 里进入「设置 → 代理」，粘贴参数后点「检查并保存到这台 Mac」。检查通过后参数会保存到本机，需要让系统应用使用它时，再点「开始使用这台 Mac 上网」。有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发，密码进入 macOS Keychain，不写进 shell 历史、日志或发布包。正式改系统代理前会备份原网络设置，失败或不用时可以恢复。

边界也很清楚：Netfix 不卖代理，不内置节点，不承诺第三方服务一定可达，也不承诺任何特定出口质量。它只帮你解析、预检、保存、部署、监控和恢复你自己已有的连接参数。

**暂不支持** `ss://`、`vmess://` 或 Clash/sing-box 订阅链接。

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

## AI 问答怎么接

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

给 Agent 的参数写法里会出现 `mode: "image_question"`、`upload_confirmed: true` 和 `data:image/...`。DeepSeek 是默认文本解释主力；图片链路走 MiniMax、Kimi/Moonshot 或 Qwen，不能把 DeepSeek 说成图片/视觉模型。MCP 不能保存 API Key 或代理密码，只调用本地 Netfix 服务。

---

## 功能概览

| 能力 | 普通用户看到什么 | 开发者接口 |
|---|---|---|
| 一键诊断 | 哪一层坏了，下一步点什么 | `python3 netfix.py codex --json` |
| 代理粘贴部署 | 粘贴参数、预检、保存、部署、恢复 | `proxy`, `proxy-monitor`, `proxy-switch` |
| AI 解释 | 可选云端解释，先脱敏再发送 | 本地 HTTP API / MCP |
| 健康维护 | 节点异常、IPv6/TLS/DNS 问题提示 | `watch`, `report`, `logs` |
| Agent 接入 | Codex / Kimi / Claude / Cursor 可复制注册命令 | `netfix/mcp_server.py` |
| 安全回滚 | 改系统代理前备份，失败可恢复 | `fix`, `rollback`, journal |

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
├── netfix.py              CLI 入口
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
- 新的代理核心适配器，放到 `netfix/cores/`。
- 更清楚的界面文案、截图和安装说明。

提交前请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。GitHub Issue 里不要贴真实代理密码、API Key、二维码、cookie、bearer token 或原始报告。

---

## License

MIT
