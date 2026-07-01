# Next Dialogue Startup Prompt - Product Cold Audit - 2026-06-25

Copy this into a fresh Codex/GPT dialogue.

```text
你现在接手 `<repo>` 的 netfix 产品化目标。不要从“工程功能已经很多”这个角度自嗨，要从普通小白客户、会骂人的产品经理、顶级工程师和愿不愿意掏钱的真实市场视角冷审核、重构和落地。

## 终极目标

把 netfix 从工程诊断工具推进到本机顺畅可用、普通人能理解、愿意付费下载的 macOS 本地网络急诊产品候选版。第一优先不是继续堆功能，而是把用户首次打开、诊断、问 AI、配置代理、看结果、下一步操作这些路径做得像成熟产品，不让客户看到一堆工程垃圾。

## 最新原话压力锚点

用户最新批评必须作为最高产品判断锚点，不要洗白：

> 你现在这个狗屎前端，不说人话不干人事，纯粹他妈的傻逼，我是产品经理我骂死你，给小白用的东西，都接入llmapi了，搞一大堆人看都看不懂的，还什么openai正常返回401，你告诉我客户需要看到这种玩意吗，臭几把傻逼，又丑又难用，产品力一点没有跟狗屎一样，给新对话写启动提示让他顺着我的原话宏观对抗性客户角度产品经理产品力角度冷审核。我说白了这种垃圾你是客户你愿意掏钱吗。傻逼！

这句话的意思不是要求情绪回应，而是要求行动：
- 不要把 HTTP 401、provider raw status、diagnostic internal id、token field、schema_version、Keychain account、OpenAI-compatible 等工程语言直接暴露给小白。
- 不要因为 LLM API 接上了就认为产品完成。接上只是底层能力，产品价值是“我遇到网络问题，它告诉我该怎么办，并安全地帮我做完”。
- 不要再围绕 release readiness 原地打转。当前阶段先把本机使用体验做顺。
- 任何页面都要问：如果我是客户，我愿意为这个界面付钱吗？

## 先读顺序

先读这些文件，不要凭记忆改：

1. `<repo>/docs/PRODUCT_SEED_USER_WORDS_2026_06_24.md`
2. `<repo>/output/playwright/netfix-local-audit/audit-notes.md`
3. `<repo>/gui/web/index.html`
4. `<repo>/gui/macos/Sources/Views/DashboardView.swift`
5. `<repo>/gui/macos/Sources/Views/SettingsView.swift`
6. `<repo>/netfix/api.py`
7. `<repo>/netfix/llm_explain.py`
8. `<repo>/netfix/deepseek_sidecar.py`
9. `<repo>/README.md`

然后运行或确认：

```bash
python3 netfix.py server --host 127.0.0.1 --port 0
python3 -m pytest -q
swift build  # cwd: <repo>/gui/macos
```

## 当前已验证事实

- DeepSeek 侧车本机可用，`ds --doctor` 选择 `deepseek-v4-pro`。
- Netfix 已新增显式导入 DeepSeek 侧车 `.env` Key 的路径：`/llm/import-deepseek-sidecar-key`。
- Netfix 当前可以把 DeepSeek Key 写入 macOS Keychain account `deepseek`。
- 本机 live `/llm/chain-test` 已跑通过 DeepSeek 文本链路，模型 `deepseek-v4-pro`。
- Web 已加按钮「导入 DeepSeek 侧车 Key」。
- Web 已把保存的 proxy Profile 列表改成默认显示 5 个，其余折叠。
- 这些只是底层可用性改善，不等于产品体验合格。

## 当前最大产品问题

现在产品最大问题不是缺少能力，而是能力被工程噪音包住：

- 小白不懂“OpenAI 正常返回 401”这种话。它应该被翻译成“OpenAI API Key 没配或无效；如果你只是想修 ChatGPT 网页，不需要处理这个”。
- 小白不懂 provider chain、Keychain account、response_format、schema_version、HTTP status、token field。
- UI 把“系统内部状态”当主角，而不是把“下一步该做什么”当主角。
- 住宅代理/自定义代理场景有价值，但按钮太多、术语太多、危险操作和普通操作混在一起。
- LLM 应该成为“解释器和客服”，不是又多一块设置表单。

## 第一执行切片

先做一个对抗性产品冷审核，必须用截图证据，不要只写观点：

1. 启动本地 Web 控制台。
2. 用 Playwright 截图以下路径：
   - 首屏诊断状态。
   - 用户点击「检查 AI/开发工具连接」后的结果。
   - AI 解释区域。
   - 住宅/自定义代理配置区域。
   - 日志/报告区域。
3. 从三种视角逐屏标注：
   - 小白客户：我看得懂吗？知道下一步吗？敢点吗？
   - 产品经理：这像能卖钱的产品吗？价值主张是否清楚？有没有让人想退款的地方？
   - 顶级工程师：哪些真实状态需要保留，哪些应该移到高级详情？
4. 输出一个 P0/P1/P2 问题清单，但 P0/P1 必须马上改，不许只写报告。

优先修这些：

- 把用户可见诊断结果从工程状态翻译成人话。
- 把 “OpenAI 401 / GitHub fail / DeepSeek ok” 改成分层用户语言：网页访问、API Key、代理节点、DNS、系统代理。
- 首屏加一句清晰判断：例如“你的网络本身可用，但 OpenAI API Key 没配；如果你只是用 ChatGPT 网页，可以忽略 API Key 问题。”
- 把高级详情折叠到“技术详情”，默认隐藏。
- AI 区域默认只显示：
  - 当前 AI：DeepSeek 已连接 / 未连接
  - 一个问题输入框
  - 一个「解释当前问题」按钮
  - 一个「高级设置」折叠区
- 代理区默认只显示：
  - 粘贴供应商给你的 host/port/user/pass
  - 预检
  - 保存并监控
  - 当前状态
  - 高级导出/系统应用默认折叠，并明确风险。

## 工作模式

- 先运行当前产品，截图，再改。
- 修改前先找本地已有模式，别重写全项目。
- 每一处 UI 文案都要问“客户能不能看懂”；不能看懂就移到高级详情。
- Codex 主线程负责最终集成和验证。
- 可以按需开 native subagents 做截图审计、代码调查、测试补充。
- 可以调用 `cc` 做产品/架构冷审，调用 `ds` 做工程逻辑和风险冷审，调用 `gm` 做前端视觉/小白体验审查；侧车是 advisory，最终必须本地验证。
- 不要把侧车意见当事实；必须用当前文件、运行截图、测试输出验证。

## 禁止事项

- 禁止继续把 release readiness 当主线来逃避产品体验问题。
- 禁止把工程内部错误原样展示给小白。
- 禁止把“功能存在”当“产品可用”。
- 禁止为了测试通过保留难懂文案。
- 禁止执行 Tier 2 系统代理变更，除非用户明确确认。
- 禁止打印、记录、回显 API Key、代理密码、token。
- 禁止删除或移动 `iphone-v2rayn-package-2026-06-14*`，除非用户明确允许。
- 禁止声称付费外发 ready；Developer ID、公证、clean-machine QA、法务、完整 live provider smoke 仍是外部阻塞。

## 验收标准

本阶段验收不是“所有发布门禁通过”，而是“本机顺滑可用”：

- 小白打开 Web 或 macOS app 后，能在 10 秒内知道当前问题是什么、下一步点什么。
- 常见工程状态必须有人话解释。
- LLM DeepSeek 文本解释链路可用，导入侧车 key 后不用再复制粘贴 API Key。
- 「问 AI」默认能解释当前报告；没有报告时应引导先诊断，而不是报错。
- 高级技术详情默认折叠。
- 住宅/自定义代理主流程清楚：粘贴 -> 预检 -> 保存并监控 -> 状态 -> 修复建议。
- Web 通过 Playwright 截图检查：无明显遮挡、无长列表淹没主流程、console 无明显资源/表单错误。
- 验证命令至少包括：
  - `python3 -m pytest -q`
  - `swift build`
  - `python3 scripts/marketing_claims_check.py --json`
  - 本地 live `/llm/chain-test` DeepSeek 文本链路

## 停机条件

如果缺少真实 API Key、Keychain 权限、浏览器自动化权限、Apple 签名/公证凭证，明确说缺什么，不要伪造。

如果产品页面仍然让小白看到 HTTP 401、raw provider status、schema、token field、Keychain account 等默认信息，就不要声称本阶段完成。
```

