# Product Seed - User Words - 2026-06-24

This file preserves the user's raw product seed for the next productization goal.

## Raw Seed

> 现在还不是好用的产品，好多功能不能实现，点击日志也没有反应，这应该是一个web还是本地软件呢，我之前想要接入llm的api也没有接入啊，感觉不是刻意成熟的有很强大产品力的产品啊，我们不能局限于这些功能吧，叫claude code宏观对抗性冷审核，开agentteam研究好，设计好，为下一阶段的完善冲刺设计好，完善好，落地好执行好，这个goal结束之后我要得到一个可以直接往外发，可以宣传可以让别人愿意花钱付费下载即用好用的东西，不能自嗨，各种复杂压力场景都要完成甚至我觉得应该能够客户买了住宅IP之后（一般网站都会给个什么用户密码和端口之类的，用户只需要复制粘贴到我们的软件上，电脑会自动部署好这个干净的住宅ip并持续的监控维护，相关功能好好研究一下，我们不卖住宅ip，我们帮助普通人部署维护修复等等，）保留我的原话种子，开满子智能体，叫上claudecode和kimi一起搜索研究好落地好设计好完善好，前端设计之类的也要好，规划好任务步骤 开goal

> llm的接入肯定优先选择国内的，比如deepseek，kimi或者minimax，尤其是deepseek很便宜量大管饱，缺点是没有多模态，用户有问题没办法发图片问，反正llm的接入相关要做好国内模型的适配

## Non-Negotiables

- The product must not stay a self-referential diagnostic demo.
- The final goal output must be a product candidate that can be shared externally, explained clearly, and tried by a paying user.
- The product surface must decide whether it is primarily a local desktop app, a web UI, or a hybrid local app with embedded web UI.
- LLM API integration must be real, optional, productized, and domestic-provider-first.
- DeepSeek should be treated as the low-cost text-first default, while Kimi/Moonshot, MiniMax, and Qwen provide domestic fallback and multimodal adaptation paths.
- Image-question workflows must not assume DeepSeek multimodal support; screenshots need a validated multimodal domestic provider or a clear fallback.
- Residential proxy deployment and maintenance is a first-class scenario: users paste provider credentials/host/port, and netfix configures, monitors, verifies, repairs, and explains the setup.
- netfix does not sell residential IPs; it helps users deploy, validate, maintain, and repair legally obtained proxy credentials.
- Complex pressure scenarios must be designed and tested, not hand-waved.
- Claude Code, Kimi Code, and native subagents may provide critique and evidence, but Codex remains the integrator and verifier.
