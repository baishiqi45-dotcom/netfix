# Netfix

[English README](README.en.md)

![Netfix macOS 本地网络急诊工具](assets/github/hero.zh.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: local first](https://img.shields.io/badge/privacy-local--first-0f766e)
![agent: MCP ready](https://img.shields.io/badge/agent-MCP%20ready-111827)

macOS 上 Codex / ChatGPT / GitHub 突然连不上时，Netfix 先告诉你卡在哪一层：DNS、系统代理、代理核心、IPv6、TLS、目标服务，还是你保存的代理参数本身有问题。

Netfix 的目标不是让用户学会命令行，而是把本地网络急诊做成一个能点开的工具：一键诊断，人话解释，确认后修复，出问题能恢复原网络设置。

## 它解决什么

- AI 和开发工具突然连不上，不知道是网络、代理、DNS 还是服务端问题。
- 买到或自建了代理服务，只拿到 `host:port:user:pass`，不知道怎么安全配置到 Mac。
- 代理一会儿通一会儿断，想知道出口、目标服务、IPv6、TLS 哪一步坏了。
- Codex / Kimi / Claude 等 Agent 需要结构化诊断，不想让模型自己猜命令。
- 不想把代理密码、API Key、原始日志发到云端。

## 现在能怎么用

当前仓库优先保证源码开源、可审计、可本地运行。公开签名 `.dmg` 还没有完成 Developer ID 签名和公证，所以不要把本地候选包宣传成正式下载版。

给别人一行命令接入 Codex MCP。当前使用 `v0.2.0-qa.1` 的 release 资产地址，避免 GitHub raw main 缓存延迟：

```bash
curl -fsSL https://github.com/baishiqi45-dotcom/netfix/releases/download/v0.2.0-qa.1/install_codex_mcp_from_github.sh | bash
```

这条命令会下载源码到 `~/.netfix/netfix-codex-mcp-source`，做 MCP 初始化检查，并执行 `codex mcp add netfix -- python3 .../netfix/mcp_server.py`。完成后需要重启 Codex 或新开 Codex 线程。它不会复制代理密码或 API Key。

给普通 Mac 用户一行安装本地 App。当前默认下载的是 `v0.2.0-qa.1` 里的 unsigned QA DMG：

```bash
curl -fsSL https://github.com/baishiqi45-dotcom/netfix/releases/download/v0.2.0-qa.1/install_mac_app_from_github.sh | bash
```

这条命令会下载 DMG、校验 SHA256、安装 `Netfix.app` 到 `~/Applications`、如果本机有 Codex CLI 会顺手注册 Netfix MCP，然后打开 App。当前 QA DMG 还没有 Developer ID 签名和公证，所以现在能做到“技术用户一行安装”，还不能包装成“普通小白稳定可用的正式安装命令”。

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

## 代理到底复制什么

不要复制“当前出口 IP”。出口 IP 只是检测结果，不能拿来连接。

请从你自己合法获得的代理服务后台复制连接参数。Netfix 支持常见写法：

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

在 App 里进入「设置 → 代理」，粘贴参数后先点「预检」。预检通过后再保存到这台 Mac，需要让系统应用使用它时，再点「部署到这台 Mac」。有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发，密码进入 macOS Keychain，不写进 shell 历史、日志或发布包。部署前会备份原网络设置，失败或不用时可以恢复。

边界也很清楚：Netfix 不卖代理，不内置节点，不承诺第三方服务一定可达，不承诺所谓干净住宅 IP。它只帮你解析、预检、保存、部署、监控你自己已有的连接参数。

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

## 接进 Codex / Kimi

已经安装 App 的用户不用找仓库脚本：

1. 打开 Netfix。
2. 进入「设置 → Agent → 复制给 Codex」，把命令粘到 Codex 终端里，重启 Codex。
3. 如果你用 Kimi，点「复制 Kimi/通用配置」。当前部分 Kimi Code CLI 版本没有 `mcp add` 命令，不要粘贴旧命令；把通用 stdio 配置填到支持 MCP 的 Kimi/Agent 宿主里。

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

Kimi/通用 MCP stdio 配置：

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
| Agent 接入 | Codex / Kimi 可复制注册命令 | `netfix/mcp_server.py` |
| 安全回滚 | 改系统代理前备份，失败可恢复 | `fix`, `rollback`, journal |

## 安全边界

- 本地优先：诊断和规则推断不依赖外网 LLM。
- 低风险修复可直接执行；会改系统配置的修复必须用户确认。
- 代理密码和 API Key 不进报告、截图、日志、导出包或 GitHub Issue。
- 图片问诊不会自动识别图片像素里的可见密码，上传前用户必须自己确认已脱敏。
- Netfix 不提供代理服务，不承诺第三方服务质量，不帮助绕过第三方账号、风控或滥用控制。

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
