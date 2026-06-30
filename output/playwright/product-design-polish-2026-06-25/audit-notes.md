# Netfix Web UI Product Polish Audit - 2026-06-25

## Scope

- Surface: `gui/web/index.html`
- Flow: first visit, one-click check, result state, AI explanation entry, network line entry
- Guardrail: UI/copy/tests only. No Tier 2/system network changes were executed.

## Inputs Accepted

- Kimi ordinary target-customer critique: accepted as the baseline user voice.
- Read-only subagent findings:
  - Ordinary customer audit: accepted P0/P1 defaults and terminology findings.
  - PM audit: accepted goal-first flow and no auto-rendering old result.
  - Engineering audit: accepted JS binding and timeout/state risks.

## Implemented Changes

1. Rebuilt the default first screen around user goals:
   - `ChatGPT 网页打不开`
   - `Codex / OpenAI 报错`
   - `GitHub / Copilot 连不上`
   - `都连不上 / 不确定`

2. Hid operational modules by default:
   - AI explanation panel hidden until requested.
   - Network line panel hidden until requested.
   - Running records hidden until result/failure path.

3. Removed confusing default terms from visible user paths:
   - `Tier` -> low-risk/needs-confirmation language.
   - `诊断报告/报告` -> `检查结果`.
   - `日志` -> `运行记录`.
   - `代理/桥接` -> `网络线路/本机转发` in user-facing copy.
   - `API Key` -> `账号密钥`.

4. Changed result behavior:
   - Startup no longer auto-renders the latest report as the current state.
   - Result primary actions are based on the check outcome.
   - Technical details are folded under `给技术人员看的信息`.
   - Backend explanation text is sanitized before display.

5. Fixed engineering risks:
   - One-click check timeout increased from 20s to 60s.
   - Failure now updates the main summary instead of leaving it stuck in running state.
   - Proxy repair action buttons now use `data-*` binding instead of inline JS string interpolation.
   - AI advanced settings id now points to the correct panel.

## Browser Evidence

- Initial old screenshot: `01-browser-initial-viewport.png`
- Final desktop home: `02-after-home-viewport.png`
- Final result state: `03-after-result-viewport.png`
- Network line entry opened: `04-assist-entry-expanded.png`
- Mobile home: `05-mobile-home.png`

## Browser Checks

- Desktop home:
  - AI, network line, running records, and recovery panels hidden by default.
  - Visible bad-term scan empty for: `Tier`, `开始急诊`, `日志/报告`, `最新报告`, `诊断报告`, `API Key`, `本地引擎`, `代理`.

- Result state:
  - Summary: `网络看起来正常 当前所有检查都通过了，没有发现明显的网络问题。`
  - Services: `ChatGPT 网页`, `Codex / OpenAI`, `GitHub / Copilot`.
  - Visible bad-term scan empty.

- Network line entry:
  - Opens only on demand.
  - Backend lifecycle copy is displayed as `本机转发` / `网络线路`.
  - Default target profile is `AI / 开发工具`.

- Mobile home:
  - No horizontal overflow.
  - Goal options and primary actions fit in the viewport.
  - Visible bad-term scan empty.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_web_ui
node -e "const fs=require('fs'); const html=fs.readFileSync('gui/web/index.html','utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]).join('\n'); new Function(scripts); console.log('embedded JS syntax OK')"
rg -n "执行 Tier|Tier 1|开始急诊|诊断中|正在检查网络路径|导入 DeepSeek 侧车 Key|配置 Key|日志/报告|最新报告|诊断报告|事件日志|本地引擎|保存完整代理身份报告|一键诊断" gui/web/index.html tests/test_web_ui.py scripts/verify_dmg_backend.sh
```

All checks passed. The final `rg` output only matches negative test assertions.
