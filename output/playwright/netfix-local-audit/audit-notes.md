# Netfix Local Usability Cold Audit - 2026-06-25

## Scope

- Surface: local Web console at `http://127.0.0.1:50120/`.
- Flow: AI setup, DeepSeek sidecar key import, LLM readiness, saved proxy profile panel.
- Evidence:
  - `01-home-full.png`: pre-fix long profile list and AI readiness surface.
  - `02-after-llm-profile-collapse.png`: profile list collapsed to first five plus details.
  - `03-final-clean-web.png`: final clean Web screenshot after favicon/password-form console cleanup.

## Product Manager View

- The product direction is clearer now: DeepSeek is the low-cost text default; image question is explicitly disabled until MiniMax/Kimi/Qwen keys and the feature gate exist.
- The old gap was fatal for local use: DS sidecar had a working key, but Netfix could not reuse it. Netfix now has an explicit import path into Keychain and a visible Web/macOS control.
- Saved proxy Profiles can accumulate quickly. Showing all profiles by default buried the main flow; the Web console now shows five and folds the rest.

## Senior Engineer View

- Fixed a real Keychain bug: `security add-generic-password -w` did not accept the previous stdin approach as intended, creating an empty secret. Netfix now writes a usable secret and treats empty LLM Keychain items as not ready.
- `/llm/test` and `/llm/chain-test` now use strict JSON-oriented prompts. Live DeepSeek chain-test passed with `deepseek-v4-pro`.
- Readiness now shows the active provider model from settings, so DS sidecar import no longer displays `deepseek-v4-flash` while calling `deepseek-v4-pro`.
- Remaining risk: Keychain writes through the macOS `security` CLI require the password as the `-w` argument. Output is captured and not logged, but a future native helper would be cleaner.

## Novice Customer View

- A user can now click "导入 DeepSeek 侧车 Key" instead of finding and pasting an API key again.
- The AI panel states DeepSeek is ready and image-question is disabled, which is understandable and prevents false expectations.
- The proxy panel is less overwhelming after profile folding, but still has many advanced buttons. Next polish should group advanced profile actions behind a menu or details block.

## Verification

- DS sidecar doctor selected `deepseek-v4-pro` and returned `DS_ROUTE_OK`.
- Netfix imported the sidecar key into Keychain account `deepseek` without printing the key.
- Live `/llm/chain-test` returned ok for DeepSeek text mode with `deepseek-v4-pro`.
- Web console loaded without favicon or password-form console errors after cleanup.
