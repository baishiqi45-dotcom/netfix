# netfix 开源/产品化计划

## 1. 开源定位

- **仓库名**：`netfix`（或 `netfix-macos`）
- **目标用户**：macOS 上依赖海外 AI/开发/常用服务的普通用户与开发者，尤其是中国大陆网络环境。
- **核心卖点**：离线可用、小白能用的菜单栏 App、国产 Agent 一句话调用。
- **License**：MIT（宽松，便于二次开发）。

## 2. 首次开源 Checklist

1. 注册 GitHub 仓库，push 当前代码。
2. 完善 README 中英文双语（目前中文为主，补充英文版或至少英文 Quick Start）。
3. 添加 `CONTRIBUTING.md`：
   - 如何新增症状规则（`rules/symptoms.json`）
   - 如何新增 core 适配器（`netfix/cores/`）
   - 如何新增服务分组（`rules/services.json`）
   - 如何提交 case（`cases/`）
4. 配置 GitHub Actions CI：
   - `python3 -m py_compile`
   - `python3 -m unittest discover tests`
   - CLI / API / MCP / Web 仪表盘 smoke tests
   - SwiftUI menu bar app build on macOS runners
   - 已添加 `.github/workflows/ci.yml`
5. 添加本地开发入口：
   - `Makefile`：`make lint/test/smoke/api-smoke/mcp-smoke/app/case`
   - `CONTRIBUTING.md`
6. 发布 v0.2.0 tag，提供四种使用方式：
   - `git clone` + 浏览器打开 Web 仪表盘
   - `git clone` + `python3 netfix.py`
   - `pipx install .` 生成 `netfix` 全局命令
   - 自行编译 SwiftUI 菜单栏 App（`cd gui/macos && swift build`）

## 3. 社区运营

- 用 GitHub Issues 收集真实故障场景，标签化：`client:v2rayN`、`client:clash`、`dns`、`mtu`、`wi-fi`、`gui`、`agent`。
- 鼓励用户提交 `cases/YYYY-MMDD-<关键词>.md`，反哺规则库。
- 每季度根据 case 数量决定是否新增 specialist subcommand（如 `netfix dns`、`netfix proxy`）。

## 4. 产品化路径（可选）

| 阶段 | 产物 | 商业模式 |
|---|---|---|
| v0.1 | 开源 CLI | 免费 |
| v0.2 | CLI + Web 仪表盘 + SwiftUI 菜单栏原型 + MCP | 免费 / GitHub Sponsors |
| v0.5 | 签名/公证的 `.app` 安装包、节点健康监控 + cron 自动体检 | 捐赠 / GitHub Sponsors |
| v1.0 | 带 onboarding 的 macOS App Store 应用 | App Store 付费 / 订阅 |
| 企业版 | 审计日志、集中报表、LDAP/SSO | 按席位授权 |

## 5. 风险与边界

- 不实现/不鼓励新的翻墙协议，只做诊断和本地修复。
- 不收集用户代理凭据，所有配置读取在本地完成。
- 对 GUI 客户端的自动切换能力受限（如 v2rayN 无外置 API），需在文档中明确；App 中通过 AppleScript 重启 GUI 作为折中。
- 签名/公证需要 Apple Developer Program，开源仓库只提供未签名构建指引。
