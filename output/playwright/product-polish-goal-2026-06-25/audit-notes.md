# 2026-06-25 Netfix 产品力完善落地记录

## 范围

- 目标：继续修复上一轮冷审暴露的 P0/P1 产品力问题，不做删除、迁移、提交、外部发布或账号/付费动作。
- 运行地址：`http://127.0.0.1:55819/`
- Browser 插件可用于 DOM/控制台检查，但截图接口超时；视觉截图回退到本机 Node Playwright。

## 发现并修复的问题

1. 诊断摘要重复同一句根因，用户看不到真正下一步。
   - 修复：新增 `buildReportViewModel()` 和 `renderReportSummary()`，把根因、下一步、主动作和技术详情拆开。
   - 结果：同一句 OpenAI/API Key 根因不会重复；技术字段默认折叠。

2. 根因 ID 不稳定时，“配置 API Key”动作可能缺失。
   - 修复：前端不只依赖 `root.id`，同时用 OpenAI/API Key 文案兜底识别。

3. 检查完成后“本地网络 / DNS”仍显示“待检测”，会让用户误以为没有查完。
   - 修复：有诊断结果但该层无异常时显示“未见异常”。

4. 用户点击“开始急诊”后十几秒没有稳定 loading 反馈。
   - 修复：按钮显示“诊断中...”，状态条显示“正在诊断...”，摘要卡显示进行中说明，并用 `operationInProgress` 防止启动时报告刷新覆盖 loading 状态。

5. 服务检查排序受后端返回顺序影响。
   - 修复：固定为 ChatGPT 网页、OpenAI API Key、Codex、GitHub、Claude/Gemini。

## 证据

- Loading 状态：`output/playwright/product-polish-goal-2026-06-25/05-loading-state.png`
- 当前桌面完成态：`output/playwright/product-polish-goal-2026-06-25/08-desktop-final-current.png`
- 当前移动完成态：`output/playwright/product-polish-goal-2026-06-25/09-mobile-final-current.png`

## 验证

- Browser DOM/console：页面加载、诊断交互、控制台 warn/error 检查通过；截图接口两次超时。
- Node Playwright：桌面 1280x720、移动 390x844 截图通过；无横向溢出；控制台 0 warning/error。
- `python3 - <<'PY' | node --check -`：通过。
- `python3 -m py_compile netfix/reasoner.py netfix/explain.py netfix/api.py`：通过。
- `python3 -m pytest tests/test_web_ui.py::TestWebUI::test_web_ui_renders_product_actions_and_safe_fix_commands -q`：通过。
- `python3 -m pytest -q`：341 passed。
- `python3 scripts/marketing_claims_check.py --json`：29 checked，0 findings。
