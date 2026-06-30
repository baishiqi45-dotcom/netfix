# 2026-06-25 Netfix 产品冷审记录

## 输入

- 启动文档：`docs/NEXT_DIALOGUE_START_PROMPT_PRODUCT_COLD_AUDIT_2026_06_25.md`
- 目标：用普通目标客户视角和多角度子智能体审查 Netfix 当前产品力，并把 P0 问题落地到界面。
- 本地验证地址：`http://127.0.0.1:55819/`

## 锐评结论

- 普通客户不会为“调试面板”付费，只会为“告诉我为什么 AI 工具连不上，并安全修好”付费。
- 原界面把 Provider、Base URL、Model、API Key、Keychain、401、raw status、Profile 操作、技术日志等实现细节前置，导致首屏看起来像工程师工具。
- 代理配置区的按钮过多，用户分不清“验证”“保存”“应用系统代理”“导出”“删除”的风险边界。
- 日志区默认黑底原文过重，削弱了“已诊断、有结论、可行动”的产品感。

## 子智能体分工

- Volta：普通目标客户视角，判断是否愿意付费和哪里会放弃。
- Curie：产品经理视角，重排首屏、AI 解释入口、代理主流程。
- Carson：工程视角，梳理哪些字段应默认隐藏、哪些只能放技术细节。
- Banach：视觉和布局视角，指出侧栏负担、按钮密度、窄屏风险。
- Singer：住宅代理用户视角，要求主流程变成“粘贴 -> 预检 -> 保存并监控”。
- Kimi：扮演最普通目标客户，结论是“不愿付费”，核心原因是界面像调试器而非急诊产品。

## 已落地改动

- 首屏标题改为“Netfix：AI 工具连不上，一键查原因并给修法”，CTA 改为“开始急诊”。
- 服务名称改成人话标签，例如 ChatGPT 网页、OpenAI API Key、GitHub API。
- OpenAI 401 根因改成“网络能连到 OpenAI，但 API Key 没配好；如果只是修 ChatGPT 网页，可以先忽略这个”。
- AI 面板默认只保留状态、问题输入和“解释当前问题”，Provider/Base URL/Model/API Key/预算/图片问诊收进高级设置。
- AI 链路状态和测试结果改成人话；fallback chain、redaction audit、官方文档核验、Keychain 等仅在技术或高级细节中出现。
- 日志面板默认展示摘要；技术日志、历史记录、文件路径、隐私设置、删除全部本地数据都折叠。
- 代理面板改为导入已有代理凭据，主按钮为预检、保存并监控；保存后的系统应用、导出、删除等动作折叠到更多/危险操作。

## 证据

- 初始截图：`output/playwright/product-cold-audit-2026-06-25/01-home-full-before.png`
- 诊断后截图：`output/playwright/product-cold-audit-2026-06-25/02-after-diagnose-full-before.png`
- AI 面板改造前：`output/playwright/product-cold-audit-2026-06-25/03-ai-panel-before.png`
- 代理面板改造前：`output/playwright/product-cold-audit-2026-06-25/04-proxy-panel-before.png`
- 日志面板改造前：`output/playwright/product-cold-audit-2026-06-25/05-logs-panel-before.png`
- 改造后首屏：`output/playwright/product-cold-audit-2026-06-25/07-home-full-after-log-clean.png`

## 验证

- 浏览器控制台：改造后 0 warning / 0 error。
- `python3 -m py_compile netfix/reasoner.py netfix/explain.py netfix/api.py` 通过。
- `swift build` 通过。
- `python3 scripts/marketing_claims_check.py --json` 通过。
- DeepSeek 文本链路实测通过；其他未配置 Key 的供应商按预期跳过。
- `python3 -m pytest -q` 通过：341 passed。
