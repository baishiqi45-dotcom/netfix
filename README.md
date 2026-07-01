# Netfix

[English README](README.en.md)

![Netfix macOS 本地网络急诊工具](assets/github/hero.zh.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: local first](https://img.shields.io/badge/privacy-local--first-0f766e)
![agent: MCP ready](https://img.shields.io/badge/agent-MCP%20ready-111827)

## 它做什么

已有合法代理参数但不会配置 Mac？Netfix 让你粘贴一整行连接信息，先检查能不能用，再保存到本机，最后由你确认是否让这台 Mac 开始使用。

macOS 上 Codex / ChatGPT / GitHub / 任何 API 客户端突然连不上时，**Netfix 也会告诉你卡在哪一层**：
DNS、系统代理、代理核心（xray / sing-box / mihomo / Clash）、IPv6、TLS、目标服务，还是你粘贴的代理参数本身有问题。
然后让你点确认才改网络，改完可以一键回滚。
不需要 API Key 也能用，需要时也只是把**本地脱敏后的诊断**发给云端模型重新说人话。

## 60 秒开始

```bash
# 一行装 macOS App（QA 版本，未签名；首次启动在「系统设置 → 隐私与安全性」点「仍要打开」）
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

# 开发者 / Agent 用户再用：一行把 MCP 自动接入 Codex；Kimi / Claude / Cursor 按下方手动配置
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

源码装：

```bash
pip install -e .
python3 netfix.py codex --json
```

## 跟现有工具比

| 工具 | 它做什么 | Netfix 多做的事 |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | 客户端代理 App：你提供节点，它们转发流量 | Netfix 告诉你**这台 Mac 现在的网络到底能不能让代理连上**，应用前预检，失败可回滚 |
| **Activity Monitor / `netstat`** | 通用进程/端口检查 | 一份报告同时覆盖 DNS / 系统代理 / 代理核心 / IPv6 / TLS / 目标服务，告诉你"坏在哪一层" |
| **聊天机器人手写 `curl` / `ping`** | 模型临时拼命令 | 结构化 JSON 输出、分级修复、自动备份原网络、发云端前先脱敏 |
| **网络监控小部件** | 看实时速率/信号 | 修复向：粘贴参数 → 预检 → 部署 → 监控 → 还原，一条龙 |

## 它不做什么

- **不卖代理，不内置节点，不承诺第三方服务质量。** Netfix 只帮你解析、预检、保存、部署、监控、恢复你自己已有的连接参数。
- **严格遵守第三方平台的账号、风险控制、地理与滥用规则；不做任何形式的规避。**
- **不会**把你的代理密码、API Key、原始报告、二维码、cookie 自动泄露到云端、shell 历史、截图或 GitHub Issue。

## 当前能怎么用

当前仓库优先保证源码开源、可审计、可本地运行。公开签名 `.dmg` 还没有完成 Developer ID 签名和公证，所以不要把本地候选包宣传成正式下载版。

给别人一行命令接入 Codex MCP。当前从 `main` 拉安装脚本，脚本默认下载 `main` 源码；如果你要锁定发布版，可以用 `NETFIX_REF` / `NETFIX_REF_KIND=tags` 指定 tag：

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

这条命令会下载源码到 `~/.netfix/netfix-codex-mcp-source`，做 MCP 初始化检查，并执行 `codex mcp add netfix -- python3 .../netfix/mcp_server.py`。完成后需要重启 Codex 或新开 Codex 线程。它不会复制代理密码或 API Key。

给普通 Mac 用户一行安装本地 App。当前从 `main` 拉安装脚本，脚本默认下载 `v0.2.0-qa.1` 里的 unsigned QA DMG：

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash
```

这条命令会下载 DMG、校验 SHA256、安装 `Netfix.app` 到 `~/Applications`、如果本机有 Codex CLI 会顺手注册 Netfix MCP，然后打开 App。当前 QA DMG 还没有 Developer ID 签名和公证，所以现在能做到"技术用户一行安装"，还不能包装成"普通小白稳定可用的正式安装命令"。

从源码目录直接试：

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

![Netfix 用户路径](assets/github/workflow.zh.png)

## 真实 case 速览

`cases/` 目录里都是脱敏后的真实场景，README 摘要几条最有共鸣的：

- **「Codex 报连不上，其实是 API Key 失效」** — 见 `cases/20260617-1405-codex-reachable-needs-key.md`。网络层一切正常，Netfix 会指出根因不在你这边。
- **「普通用户第一次部署代理的 9 个坑」** — 见 `cases/2026-06-29-普通用户代理部署体验审查.md`。粘贴参数 → 预检 → 部署 → 回滚的完整人话流程。
- **「健康基线快照」** — 见 `cases/2026-06-17-healthy-baseline.md`。问题解决前后做对照，作为以后同类故障的快速比对模板。

新 case 欢迎按 `cases/TEMPLATE.md` 提交，PR 前请读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

## 代理到底复制什么

不要复制"当前出口 IP"。出口 IP 只是检测结果，不能拿来连接。

请从你自己合法获得的代理服务后台复制连接参数。Netfix 支持常见写法：

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

在 App 里进入「设置 → 代理」，粘贴参数后先点「检查这行能不能用」。检查通过后再保存到这台 Mac，需要让系统应用使用它时，再点「开始使用这台 Mac 上网」。有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发，密码进入 macOS Keychain，不写进 shell 历史、日志或发布包。正式改系统代理前会备份原网络设置，失败或不用时可以恢复。

边界也很清楚：Netfix 不卖代理，不内置节点，不承诺第三方服务一定可达，也不承诺任何特定出口质量。它只帮你解析、预检、保存、部署、监控和恢复你自己已有的连接参数。

## FAQ

**不接 API Key 能用吗？**
能。诊断、规则解释、代理预检、保存、开始使用和恢复网络都在本地完成。API Key 只用于你主动开启云端 AI 解释时。

**会不会改坏我的网络？**
正式改系统代理前会备份原网络设置。不用时点「恢复原来的网络设置」即可还原。

**我的代理密码和 API Key 存在哪里？**
只写入 macOS Keychain，不进日志、报告、截图、发布包或 GitHub Issue。

**支持哪些代理格式？**
支持 `host:port:user:pass`、`http://user:pass@host:port`、`socks5://user:pass@host:port`、`host,port,user,pass`。暂不支持 `ss://`、`vmess://` 或 Clash/sing-box 订阅链接。

## AI 问答怎么接

不接 API 也能用。Netfix 默认用本地规则解释诊断结果。接 API 以后，云端模型只负责把脱敏报告解释成人话。

App 路径：打开「设置 → AI」，选择 DeepSeek、Kimi/Moonshot、MiniMax、Qwen 或自定义 OpenAI-compatible 供应商，贴 API Key，保存。Key 进入 Keychain。

环境变量路径：

```bash
export NETFIX_LLM_API_KEY_DEEPSEEK="sk-..."
python3 netfix.py explain --provider deepseek --json
```

本地 API 配置示例：

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

## 接进 Codex / Kimi / Claude / Cursor

已经安装 App 的用户不用找仓库脚本：

1. 打开 Netfix。
2. 进入「设置 → Agent → 复制给 Codex」，把命令粘到 Codex 终端里，重启 Codex。
3. 如果你用 Kimi，点「复制 Kimi/通用配置」。当前部分 Kimi Code CLI 版本没有 `mcp add` 命令，不要粘贴旧命令；把通用 stdio 配置填到支持 MCP 的 Kimi/Agent 宿主里。
4. Claude Desktop / Cursor：在 App 里复制 `mcp.json` 片段，粘到对应客户端的 MCP 配置文件即可（路径见 [SECURITY.md](SECURITY.md) 和 [CONTRIBUTING.md](CONTRIBUTING.md)）。

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

Kimi/Claude/Cursor 通用 MCP stdio 配置：

```yaml
name: netfix
command: python3
args:
  - /absolute/path/to/netfix/mcp_server.py
```

Agent 端标准入口：

```bash
python3 netfix.py codex --json
```

重点读 `environment.active_profile`、`diagnostics`、`root_causes`、`fixes` 和 `manual_steps`。低风险修复可以执行；会改系统配置的动作必须先让用户确认；只能手动处理的动作只给清单。

## 功能概览

| 能力 | 普通用户看到什么 | 开发者接口 |
|---|---|---|
| 一键诊断 | 哪一层坏了，下一步点什么 | `python3 netfix.py codex --json` |
| 代理粘贴部署 | 粘贴参数、预检、保存、部署、恢复 | `proxy`, `proxy-monitor`, `proxy-switch` |
| AI 解释 | 可选云端解释，先脱敏再发送 | 本地 HTTP API / MCP |
| 健康维护 | 节点异常、IPv6/TLS/DNS 问题提示 | `watch`, `report`, `logs` |
| Agent 接入 | Codex / Kimi / Claude / Cursor 可复制注册命令 | `netfix/mcp_server.py` |
| 安全回滚 | 改系统代理前备份，失败可恢复 | `fix`, `rollback`, journal |

## 安全边界

- 本地优先：诊断和规则推断不依赖外网 LLM。
- 低风险修复可直接执行；会改系统配置的修复必须用户确认。
- 代理密码和 API Key 不进报告、截图、日志、导出包或 GitHub Issue。
- 图片问诊不会自动识别图片像素里的可见密码，上传前用户必须自己确认已脱敏。
- Netfix 不提供代理服务，不承诺第三方服务质量，不帮助绕过第三方账号、风险控制或滥用控制。

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

## 贡献

欢迎提交：

- 新的脱敏 case，放到 `cases/YYYY-MM-DD-症状关键词.md`。
- 新的症状规则，改 `rules/symptoms.json`。
- 新的服务分组，改 `rules/services.json`。
- 新的代理核心适配器，放到 `netfix/cores/`。
- 更清楚的界面文案、截图和安装说明。

提交前请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。GitHub Issue 里不要贴真实代理密码、API Key、二维码、cookie、bearer token 或原始报告。

## License

MIT
