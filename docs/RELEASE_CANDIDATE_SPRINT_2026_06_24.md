# Netfix Release Candidate Sprint - 2026-06-24

> Goal: turn netfix from an engineering diagnostic tool into an externally shareable paid-product candidate.
> Seed: see `docs/PRODUCT_SEED_USER_WORDS_2026_06_24.md`.

## Product Decision

Primary product form:

**Local macOS App + local Web console.**

- The macOS App is the paid download surface.
- The local Web console is the fastest product surface for reports, logs, AI explanation, and residential proxy setup.
- CLI/API/MCP remain advanced and agent-facing surfaces.

Not chosen:

- Pure Web SaaS: cannot read or change local system proxy, DNS, routes, local ports, Keychain, proxy cores, or background monitors.
- Pure CLI: not a product normal users will pay for.
- Proxy/VPN client replacement: wrong market and higher compliance burden.

## Market Wedge

First paid wedge:

**AI/dev tool network emergency assistant for macOS.**

One-line promise:

> Codex, Claude Code, Cursor, OpenAI, GitHub, or Kimi Code cannot connect? Netfix typically tells you within 30-60 seconds whether the break is DNS, system proxy, proxy core, proxy node, PAC/WPAD, IPv6, TLS, Wi-Fi, or the remote service, then gives the safest next action.

Residential proxy is a Pro scenario, not the public headline:

- Netfix does not sell, recommend, or bundle residential IP.
- It helps users deploy, validate, monitor, and repair credentials they legally obtained elsewhere.
- Marketing must avoid "unlock", "bypass risk controls", "clean residential IP", or "anti-ban" claims.

## Evidence From Review

Six subagents, Kimi Code, and Claude Opus read-only pressure review converged on these blockers:

- Product story was too broad.
- Log/report controls must show real report paths and event state, not just toggle an empty panel.
- LLM API was not implemented.
- Residential proxy import/deploy/monitor was missing.
- Packaging still relied on system `python3`.
- Local HTTP API had no auth/CSRF story.
- Existing proxy configuration artifacts are release blockers and must not be shipped.
- Follow-up read-only reviews on 2026-06-24 refined the first public wedge: do not headline "universal network repair" or "residential IP manager"; headline "AI/dev tool connection emergency diagnosis in a typical 30-60 second run." Residential proxy stays a Pro/Beta workflow until apply/rollback/monitor persistence are real.

Kimi and Claude Opus both called out the same release risks at review time: source-side proxy artifacts, missing standalone backend runtime, no Developer ID signing/notarization, and the need for provider contract tests.

Additional read-only review on 2026-06-24 found four product-blocking gaps that were fixed in this pass:

- image-question requests were larger than the previous local API JSON body limit,
- `upload_consent: always` could bypass per-image explicit upload confirmation,
- Kimi/MiniMax vision readiness could be misreported while adapter status still said pending,
- saved reports and local `~/.netfix` metadata needed stronger redaction and file permissions.

The review also found existing source-workspace residential proxy artifacts. Those were not moved or rewritten because they are pre-existing user files, but clean release export excludes them and source release still requires strict workspace cleanup or explicit user-approved replacement with fake data.

## Landed In This Sprint

### Product Surface

- Rebuilt the local Web console around:
  - emergency dashboard,
  - real logs/reports/events,
  - diagnosis/fix failure recovery cards with retry, copy-failure-detail, and logs/report jump actions,
  - action cards with dry-run preview,
  - domestic-model LLM settings,
  - residential proxy parsing/profile apply/rollback controls.
- Upgraded the macOS App surface:
  - Onboarding now includes a first-launch privacy disclosure that explains local network reads, local report/event storage, optional cloud AI, and Tier 2 confirmation.
  - The welcome page's skip action now skips only the intro copy and still routes through privacy disclosure, permission explanation, and proxy baseline setup before onboarding can complete.
  - The first-launch proxy setup page no longer claims a proxy client was detected when `/environment` returns no `gui_client`; it uses neutral "代理客户端识别" copy and tells users they can still run baseline checks or later paste residential/custom proxy credentials.
  - Dashboard now has a real "日志" entry that opens immediately, shows loading/error state, can refresh `/logs`, opens the local log directory, and displays report path, latest summary, and events.
  - Web console "日志/报告" now opens and scrolls to the log panel instead of toggling it away, exposes a dedicated refresh control, and renders `/logs` through a live status region with loading/error/empty states.
  - `/logs` now returns a stable empty `latest_report_summary: {}` when no report exists, so Web/macOS clients can render an empty state without treating missing fields as a broken click.
  - Dashboard can request "AI 解释"; without a configured key it renders the local fallback explanation instead of silently doing nothing.
  - Settings now has an AI tab for DeepSeek/Kimi/MiniMax/Qwen/custom provider selection, Keychain-backed API key save, redaction level, upload consent, and test connection.
  - Settings now has a proxy tab for residential/custom proxy paste, parse, validate, save-to-Keychain profile flow, child-process environment preview, confirmed system apply, rollback, and monitoring.
  - Settings now has local privacy controls for latest-report saving, event-log retention days, and safe log clearing.
  - Swift Backend now parses the per-run local API token from backend stdout and passes it into APIClient; the old public `/session` token endpoint has been removed.
  - The macOS "撤销" action is now accepted by the local HTTP `/run` gate instead of failing with 403.

### Domestic LLM Layer

- Added `netfix/llm_provider.py`.
- Domestic provider order:
  1. DeepSeek,
  2. Kimi / Moonshot,
  3. MiniMax,
  4. Qwen,
  5. custom OpenAI-compatible,
  6. OpenAI fallback.
- Default is DeepSeek text explanation.
- Provider registry now records task capabilities, text/vision priority, cost tier, domestic role, image-question status, regions, provider-specific prompts, default token budget, provider payload overrides, official-doc evidence URLs, and the latest metadata check date.
- Text fallback candidate order is now DeepSeek -> Kimi -> MiniMax -> Qwen; image-question candidate order is MiniMax -> Kimi -> Qwen. The backend accepts explicitly confirmed inline `data:image/...` inputs when the experimental `image_question` feature flag is enabled; macOS Dashboard and Web console now both have consent-gated "Ask AI" flows with manual image selection and preview. The local API body limit now matches the product limit of up to three 4.5 MB images after base64 expansion, and image mode requires a per-request `upload_confirmed` flag even when text upload consent is configured as `always`. Image-question uploads now strip supported image file metadata and expose a local audit summary, but Netfix does not claim OCR or pixel-level redaction of visible text, passwords, API keys, or account identifiers.
- Qwen is now adapted as a dual-use domestic provider: `qwen-plus` remains the text fallback model, while image-question mode switches the same provider/keychain account to `qwen-vl-plus`. The default image-question chain is MiniMax -> Kimi -> Qwen; DeepSeek remains text-only.
- Kimi/Moonshot base URL now defaults to the domestic OpenAI-compatible endpoint `https://api.moonshot.cn/v1`; international accounts can manually override it to `https://api.moonshot.ai/v1`.
- DeepSeek `deepseek-v4-flash`, Kimi `kimi-k2.6`, MiniMax `MiniMax-M3`, and Qwen `qwen-plus` / `qwen-vl-plus` have official-doc metadata alignment and recorded OpenAI-compatible fixture smoke coverage. Qwen keeps `qwen-plus` for text fallback and switches to `qwen-vl-plus` only for image-question mode. Domestic provider metadata now records the 2026-06-25 official-doc check and evidence URLs. Live sandbox-key smoke is still required before marketing the feature as vendor-live verified.
- MiniMax now defaults to the domestic OpenAI-compatible `https://api.minimaxi.com/v1`; international accounts can manually switch to `https://api.minimax.io/v1`. The MiniMax-M3 payload uses `max_completion_tokens` instead of the older `max_tokens` field.
- `/llm/providers` now reports local `api_key_account`, `api_key_set`, `fallback_ready`, `text_explain_ready`, `image_question_provider_supported`, `image_question_adapter_ready`, `image_question_ready`, and `netfix_mode` metadata per provider, so the UI can show that fallback only tries providers with their own saved Keychain item or provider-scoped env key.
- `GET /llm/chain-readiness` now returns `netfix_llm_chain_readiness.v1` without calling any provider or reading out secrets. It reports the configured DeepSeek -> Kimi -> MiniMax -> Qwen text chain and MiniMax -> Kimi -> Qwen image-question chain, including each provider's Keychain account, local key readiness, model, status, official-doc metadata check date, evidence URLs, provider token field, and next step.
- Web and macOS Settings now render chain readiness directly in the AI settings surface, so users can see which domestic text and image providers will be used, skipped, or blocked before pressing "Ask AI". Missing-key rows include a "配置 Key" action that switches the form to the right provider preset and Keychain account without calling the provider. The same surface shows official-doc check date and request token field, making domestic-model adapter assumptions visible instead of hidden in code.
- Web Settings now has the same explicit cloud-AI enable/disable switch as macOS Settings. Saving Web LLM settings no longer forces `enabled: true`; when disabled, LLM calls continue to fall back to local rules and provider live tests remain refused. Web saves now also pass the provider id as `api_key_account`, and the backend now synchronizes `api_key_account` when a caller changes provider without an explicit account, keeping DeepSeek/Kimi/MiniMax/Qwen Keychain ownership explicit instead of accidentally reusing another provider's key.
- `POST /llm/chain-test` now provides an explicit domestic chain live test for DeepSeek/Kimi/MiniMax/Qwen. It requires the fixed confirmation phrase `TEST_LLM_CHAIN`, refuses to call providers when cloud AI is disabled, skips providers without their own configured key, and returns `netfix_llm_chain_test.v1` without raw provider output.
- The legacy single-provider `POST /llm/test` now also requires an explicit `TEST_LLM_PROVIDER` confirmation and refuses live provider calls while cloud AI is disabled. macOS Settings shows native confirmation dialogs before either the single-provider or full-chain test can run.
- Provider HTTP/error details are redacted before they are surfaced through local API/UI failure paths, reducing the chance that a vendor error body echoes API keys, account identifiers, emails, or inline image payloads back to the local UI. Domestic Chinese provider errors such as "请求过于频繁", "余额不足", "鉴权失败", and "模型不存在" are normalized into the same `rate_limited`, `quota_or_billing`, `auth_failed`, and `model_not_found` reason codes used by the fallback/cooldown layer.
- Kimi, MiniMax, and Qwen are marked as domestic multimodal candidates with OpenAI-compatible `image_url` payload support. macOS and Web can send selected images only after the user enables the experimental image-question flag and confirms upload.
- macOS Settings now exposes the same domestic fallback control as Web: text chain DeepSeek -> Kimi -> MiniMax -> Qwen, image chain MiniMax -> Kimi -> Qwen, with providers skipped unless their own Keychain API key or provider-scoped env key is available.
- LLM fallback responses now include a user-readable `fallback_reason_label`, so Web and macOS explain states such as "enable image question", "configure MiniMax/Kimi/Qwen API key", "rate limited", or "quota/billing issue" instead of surfacing raw internal reason codes.
- Added local LLM budget/cooldown governance:
  - default budget is 60 cloud requests/hour and 12 image-question requests/hour,
  - Web and macOS Settings expose budget controls, a separate persistence toggle, and current remaining local budget in chain readiness,
  - non-sensitive provider/mode/timestamp/cooldown ledger entries persist across backend restarts only while the local persistence toggle is enabled,
  - disabling budget persistence, disabling the budget, or deleting all local Netfix data clears the local budget ledger,
  - providers that return rate-limit or quota/billing failures enter local cooldown before another call is attempted, including after restart when the local ledger is enabled,
  - OpenAI-compatible `usage` fields are surfaced only as a non-sensitive token-count summary.
- Image-question upload now accepts only PNG, JPEG, WebP, or GIF on backend, Web, and macOS. HEIC/TIFF are rejected instead of being sent to providers with uncertain support.
- Added `scripts/provider_contract_check.py` for offline provider contract checks:
  - domestic provider order,
  - HTTPS base URLs,
  - non-empty model IDs,
  - `/chat/completions` URL construction,
  - explicit per-provider `supports_json_mode`,
  - provider capabilities and system prompts,
  - text priority and default token budgets,
  - domestic provider official-doc metadata and provider-specific token field selection,
  - `response_format` payload behavior matching provider metadata,
  - standard OpenAI-compatible JSON response parsing, including strict JSON, fenced JSON, and embedded JSON objects.
- Added `scripts/provider_smoke_check.py`:
  - default fixture mode checks DeepSeek text responses and Kimi/MiniMax/Qwen image-question responses,
  - fixture mode validates parsed `llm_explanation.v1` schema and non-sensitive usage summaries,
  - optional `--live` mode calls providers only when provider-scoped Keychain/env keys are available,
  - missing live keys are skipped unless `--require-live` is passed,
  - release evidence accepts only `mode: live`, `ok: true`, all-domestic-provider `status: ok` records for the live-provider-smoke gate; fixture or skipped results remain blockers,
  - `status` reports DeepSeek/Kimi/MiniMax/Qwen task coverage, provider-scoped Keychain/env key readiness, live-record validation, and next-step commands without reading key values or calling providers.
- Domestic LLM product direction is explicit: DeepSeek is the low-cost text-first default, while Kimi/Moonshot, MiniMax, and Qwen are domestic fallback/adaptation targets; image-question workflows must route only to providers with validated multimodal `image_url` support instead of implying DeepSeek can answer screenshots.
- DeepSeek, Kimi, and Qwen presets enable JSON mode; MiniMax stays on conservative normal chat payloads until real-provider smoke tests prove JSON-mode compatibility.
- Kimi's default general explanation model is now `kimi-k2.6`; the separate Kimi Code coding-agent route remains outside this product LLM preset.
- Kimi payloads now omit `temperature` so the preset does not send a generic `0.2` value into K2.6-specific parameter constraints.
- MiniMax's default explanation preset is now `MiniMax-M3`; multimodal remains a future product workflow until upload preview/consent and real provider tests are in place.
- Added `netfix/llm_explain.py`:
  - cloud LLM is optional,
  - report is redacted first,
  - no API key means local fallback,
  - unknown action IDs and command strings are discarded,
  - local FixEngine remains the execution authority.
- `upload_consent: ask_each_time` is now enforced: without a per-request `upload_confirmed` flag, `POST /explain_llm` returns a local fallback with `upload_consent_required` and does not call a cloud provider.
- `upload_consent: never` is enforced server-side even if a buggy client sends `upload_confirmed: true`.
- LLM responses now include `provider_used`, `fallback_chain`, and structured `failure_reason_code` values so UI and support can distinguish missing API key, auth failure, rate limit, quota/billing, model mismatch, JSON mode incompatibility, timeout, and provider outage.
- Provider-scoped temporary env keys such as `NETFIX_LLM_API_KEY_DEEPSEEK` are supported; the generic `NETFIX_LLM_API_KEY` is opt-in for the active provider only and is not reused across fallback providers.
- `POST /explain_llm` now reads the latest local report server-side instead of accepting a browser-supplied report body.
- LLM-suggested actions are sanitized against local action ids, and tier/confirmation state is rebuilt from the local report rather than trusted from the provider output.
- Web and macOS Dashboard now require an explicit confirmation before sending a redacted report to cloud AI from the "AI 解释" action.

### Privacy And Secret Handling

- Added `netfix/redaction.py`.
- Added `netfix/keychain.py`.
- Added `netfix/settings.py`.
- LLM API keys and proxy passwords are not stored in JSON settings.
- Local privacy settings now control whether `last_report.json` is retained, how long event logs are kept, and whether full residential-proxy identity reports are persisted in saved profiles.
- Report writes now apply event-log retention automatically; clearing logs does not delete settings or Keychain secrets.
- `last_report.json` is redacted before persistence, so proxy URLs supplied through env vars or `--proxy` are written with `user:***@...` rather than the original password.
- Local `~/.netfix` writes now use a private directory (`0700`) and private files (`0600`) for settings, latest report, events, proxy apply journal, IP cache, API token files, audit log, and fix journal.
- Saved proxy validation still returns full identity results to the active UI response, but the saved profile now defaults to a low-detail `last_identity_summary` instead of retaining full exit IP, ISP/ASN, and target matrix data. Web and macOS Settings expose an opt-in "保存完整代理身份报告" switch for users who explicitly want full retention.
- Reports sent to LLM remove raw stdout/stderr, commands, secrets, profile hosts, hostname, IPs, tokens, UUIDs, and sensitive query params.
- Provider output is also redacted before rendering, so echoed IPs, emails, proxy credential URLs, and long tokens cannot be written straight into the UI/log path.
- Local browser/app requests now require same-origin plus a per-server API token; cross-origin localhost control requests are rejected.
- The local Web shell uses an HttpOnly `netfix_token` SameSite cookie and no longer receives the token by server-side HTML injection.
- The macOS app and scripts receive the token through a per-process `~/.netfix/api-token-<pid>.txt` file with `0600` permissions; backend startup stdout prints only `token_file=...`, not the token value.
- `/session` now returns 410 and no longer discloses the token.
- Keychain writes now pass secrets to the macOS `security` CLI via stdin with `-w` as the last option, so API keys and proxy passwords are not placed in process arguments.
- Added a full local data clearing path:
  - `POST /data/clear` requires `confirm: DELETE_NETFIX_LOCAL_DATA`,
  - deletes latest report and event logs,
  - deletes non-secret settings,
  - deletes known Netfix LLM API Key and proxy password Keychain items,
  - exposed in Web and macOS Settings as a separate destructive action from ordinary log cleanup.
- Remaining local-control hardening gap: same-machine processes that can read the Web shell or parent stdout can still obtain the per-run token. This is acceptable for the local RC but should be revisited before high-trust enterprise positioning.
- Added `gui/macos/PrivacyInfo.xcprivacy` and package it into the local `.app` bundle.
- Added draft legal/compliance artifacts for review:
  - `docs/PRIVACY_POLICY_DRAFT.md`,
  - `docs/EULA_DRAFT.md`.
- Added `scripts/release_audit.py`:
  - workspace scope flags proxy credential/config artifacts,
  - bundle scope verifies required app files and rejects sensitive artifacts,
  - `build_app.sh --release-candidate` builds from an allowlist and hard-fails on bundle blockers,
  - `build_app.sh --release-candidate --strict-workspace` hard-fails on workspace blockers for source/repository releases.

### Residential Proxy Foundation

- Added `netfix/residential_proxy.py`.
- Supported import formats:
  - `host:port:user:pass`
  - `user:pass@host:port`
  - URL 形态：协议、用户名、密码、地址、端口
  - SOCKS 形态：协议、用户名、密码、地址、端口
  - provider table rows such as `host,port,user,password` or `host port user password`
- Added multi-line provider-list preflight through `parse_proxy_bundle` and `POST /proxy/import-preview`:
  - accepts mixed URL, `host:port:user:pass`, CSV/table, comment, and header lines,
  - returns `netfix_proxy_import_preview.v1` with valid/invalid counts, candidate rows, recommended first row, and each candidate's `deployment_decision`,
  - never saves profiles, never writes Keychain, never validates network, and never returns real passwords in the response,
  - Web console and macOS Settings expose "批量预检" and let the user either parse a candidate line or save a candidate directly with the current "保存后自动启动监控" setting.
- Parser warns about:
  - `https://proxy` vs ordinary HTTP CONNECT proxy,
  - `socks5://` local DNS leak risk,
  - percent-encoding for special characters.
- Added safe validation:
  - TCP reachability,
  - HTTP proxy probe,
  - SOCKS5 probe via existing local probe implementation,
  - 407/auth failure classification,
  - saved-profile `last_check` health state,
  - validation target URL allowlist to prevent local API abuse as an arbitrary SSRF probe.
- Added user-selectable, allowlisted validation target profiles:
  - `GET /proxy/validation-targets` returns `netfix_proxy_validation_targets.v1`,
  - `baseline` validates Google/Cloudflare/Apple captive portal probes,
  - `ai_dev` adds GitHub, OpenAI, DeepSeek, Kimi/Moonshot, and MiniMax API reachability,
  - arbitrary hosts remain blocked; target profiles are selected from a fixed server-side allowlist,
  - Web and macOS Settings expose the same validation-matrix selector for manual validation, saved-profile validation, system-apply verification, and background monitoring,
  - non-baseline matrix hard failures or unexpected target HTTP results now fail the top-level validation result instead of being shown as a clean pass.
- Added CLI `proxy-monitor` for repeated saved-profile validation and JSON health events.
- Added local API/Web/macOS App background monitor controls:
  - `GET /proxy/monitor`,
  - `POST /proxy/monitor/start`,
  - `POST /proxy/monitor/stop`,
  - `POST /proxy/profiles/<id>/delete`,
  - `POST /proxy/profiles/<id>/replace`,
  - one in-process monitor thread updates saved profile `last_check`,
  - Web and macOS can start monitoring immediately when saving a Profile, without applying system proxy or changing macOS network settings,
  - Web and macOS can update/rotate an existing Profile's host, port, username, and password from a fresh provider paste while preserving the Profile id and Keychain account; this can restart monitoring but never changes system proxy settings,
  - monitor start now persists non-secret monitor settings and API/backend startup restores enabled monitoring,
  - normal backend shutdown stops the thread without clearing the user's persisted monitor intent; explicit stop clears it,
  - proxy monitor checks append lightweight local events and structured repair actions for auth failure, endpoint timeout/DNS/refused, target-matrix failure, identity failure, or invalid local Profile; Web and macOS render safe `ui_action` buttons for update credentials, restart monitor, revalidate, import-preview, save, and export paths instead of leaving all repair actions as passive text,
  - deleting the currently monitored Profile stops the matching monitor, deleting a Profile saved as the restart auto-restore target clears that persisted monitor intent even when no monitor thread is currently running, and both paths attempt to remove the Profile's Keychain password without touching system proxy state,
  - Web and macOS Settings can start/stop/refresh/delete monitoring-related profiles and display whether auto-restore is saved,
  - Web and macOS bulk-import candidate rows now have a direct save-and-monitor action, so a common provider list can move from paste to monitored profile without the intermediate manual "use then save" step.
- Stale bridge restart now accepts authenticated SOCKS profiles as well as authenticated HTTP/HTTPS profiles, matching the confirmed system-apply bridge path. The restart still only recreates the previous local loopback bridge on the same port after explicit opt-in; it does not rewrite system proxy settings.
- Added confirmed residential proxy apply and rollback flow:
  - `POST /proxy/profiles/<id>/apply` supports `app-env` and confirmed `system` modes,
  - `system` mode requires `confirmed: true` and `confirmation: "APPLY_PROXY_PROFILE"`,
  - current macOS system proxy state is backed up before execution,
  - apply writes a dedicated proxy apply journal,
  - validation failure can auto-rollback to the backup,
  - `POST /proxy/profiles/rollback` restores the last proxy apply journal when confirmed with `ROLLBACK_PROXY_PROFILE`,
  - authenticated HTTP/HTTPS and SOCKS upstream proxies use an in-process `127.0.0.1` loopback bridge so system proxy commands never receive upstream credentials,
  - bridge status now exposes aggregate request count, active connection count, recent same-machine clients, and optional idle timeout support without recording target URLs or paths,
  - bridge state is included in apply responses and rollback journals,
  - rollback restores the previous system proxy state before stopping the bridge,
  - `GET /proxy/bridge` reports `stale_check` when system proxy still points at the last Netfix bridge,
  - `POST /proxy/bridge/recover` requires `RESTORE_STALE_PROXY_BRIDGE` and restores the pre-apply system proxy backup.
- The current safe marketing boundary is: "paste legal proxy credentials, batch-preflight common provider lists, parse, validate, save to Keychain, monitor health, export client packages, apply no-auth or authenticated HTTP/HTTPS/SOCKS residential proxies with explicit confirmation through a local loopback bridge when credentials are needed, opt-in stale bridge restart, stale-bridge recovery, and rollback." Do not market unattended system proxy rewriting, whole-device VPN replacement, or "clean residential IP" guarantees.
- `POST /proxy/validate` and `POST /proxy/profiles/<id>/validate` now accept `include_identity: true` and return a conservative identity report:
  - observed proxy exit IP via an allowlisted IP endpoint,
  - IP intelligence lookup for country/region/city, ISP/ASN, hosting/proxy/residential hints, and risk metadata when available,
  - expected-geo match result when a profile declares expected geography,
  - heuristic DNS and IPv6 leakage risk labels without claiming proof,
  - allowlisted target reachability matrix for Google/Cloudflare/Apple captive portal probes.
- Web and macOS settings surfaces now show the identity report instead of raw JSON for manual proxy validation.
- Saved profiles can export a first-class safe client configuration package through `POST /proxy/profiles/<id>/export`, Web, and macOS Settings. The response includes `package.schema_version: netfix_proxy_client_package.v1`, `README.md`, and named URL/env/Clash/Mihomo/sing-box files while preserving legacy `snippets` for compatibility. Authentication files use `<password>` placeholders and do not read the Keychain secret.
- Authenticated SOCKS system deployment is now supported through the same explicit-confirmation local HTTP loopback bridge path used for authenticated HTTP/HTTPS. Netfix writes only the local `127.0.0.1` bridge into macOS Web/Secure Web proxy settings; upstream SOCKS username/password stay in Keychain/bridge memory and are not passed to `networksetup`.
- Added a first-class `deployment_decision` contract for residential proxy paste/save/dry-run/apply flows:
  - all parse/save/apply responses now expose `schema: netfix_proxy_deployment_decision.v1`,
  - authenticated HTTP/HTTPS returns `ready` with `system_apply: bridge_required`, so the UI can explain that Netfix will save credentials to Keychain and apply a local loopback bridge after Tier 2 confirmation,
  - authenticated SOCKS returns `ready` with `system_apply: bridge_required`, so the UI can explain that Netfix will save credentials to Keychain and apply a local loopback bridge after Tier 2 confirmation,
  - no-auth SOCKS remains `ready` for system apply,
  - incomplete paste input returns `blocked` with missing fields instead of only surfacing low-level parser errors.
- Web proxy parse/apply/rollback/recover flows now render structured operation cards instead of raw JSON blobs, including explicit copy for authenticated SOCKS local bridge deployment.
- macOS Settings now decodes and renders the same deployment-decision object, so App and Web share the same product boundary and support matrix.
- Added a first-class proxy bridge lifecycle summary:
  - `GET /proxy/bridge` now returns `lifecycle.schema_version: netfix_proxy_bridge_lifecycle.v1`,
  - lifecycle states distinguish `running_system`, `running_local`, `recovery_required`, `check_failed`, `not_in_use`, and `stopped`,
  - Web renders the lifecycle card before low-level bridge details,
  - macOS Settings decodes `lifecycle`, reloads proxy/bridge state when the backend becomes ready, and shows `bridge_stop` details after rollback or stale-bridge recovery.
  - This does not silently recover or roll back on quit; automatic quit/restart handling remains a separate product decision because it writes system proxy state.
- Added a non-mutating startup bridge check:
  - backend startup calls stale-bridge detection after monitor restore,
  - `GET /proxy/bridge` exposes `startup_check.schema_version: netfix_proxy_bridge_startup_check.v1`,
  - recovery-required or check-failed startup states append a local `proxy_bridge_startup` event so Dashboard/Web logs can surface the problem even before the user manually opens proxy settings,
  - Web and macOS Settings render startup bridge warnings without performing any system proxy write.
- Added opt-in startup bridge restart:
  - `GET/POST /settings/proxy-bridge` persists non-secret bridge lifecycle preferences,
  - when `auto_restart_enabled=true`, backend startup can restart the last stale loopback bridge on the same local port if the system still points at it, the port is empty, the saved HTTP/HTTPS profile exists, and its Keychain password is available,
  - restart does not call `networksetup` and does not silently rewrite system proxy state,
  - `startup_check.auto_restart` records whether restart was skipped, blocked, failed, or completed,
  - Web and macOS Settings expose the opt-in toggle and startup restart result.
- Added a guarded macOS quit flow for bridge-dependent system proxy states:
  - `applicationShouldTerminate` queries `/proxy/bridge` before stopping the backend,
  - if system proxy is using a running Netfix bridge, the app offers "回滚系统代理后退出", "取消退出", or "仍然退出",
  - if startup/realtime detection says recovery is required, the app offers "恢复系统代理后退出", "取消退出", or "仍然退出",
  - the default safe path still requires a visible user choice; Netfix does not silently write system proxy state during quit.
- Added a menu bar bridge status surface:
  - right-click menu includes a read-only "桥接状态" line,
  - opening the menu refreshes `/proxy/bridge`,
  - status distinguishes system bridge running, local bridge running, recovery required, check failed, not in use, and stopped.
- Added bridge attention status for the macOS menu bar:
  - the menu bar status dot now gives bridge lifecycle precedence over generic diagnosis health when recovery is required, bridge checks fail, system proxy depends on Netfix, or startup auto-restart completed,
  - the app polls `/proxy/bridge` read-only while the backend is ready,
  - optional local notifications fire once for recovery-required/check-failed/auto-restarted states only when the user has enabled notifications,
  - the notification copy explicitly says auto-restart does not silently rewrite the system proxy,
  - background health/autofix notifications now also respect the same user notification toggle instead of requesting/sending notifications unconditionally.
- Added cancellable async jobs for the macOS Dashboard read-only checks:
  - `/run` async jobs now track child processes and expose `POST /jobs/<id>/cancel`,
  - cancellation terminates the running CLI child process and preserves `status: cancelled` instead of allowing a late worker result to overwrite it,
  - macOS Dashboard one-click diagnosis and service-group checks now start async jobs, poll `/jobs/<id>`, show the active job id, and expose a visible cancel button,
  - mutating fix/rollback paths remain on the existing confirmed synchronous calls rather than being made casually cancellable.

### Packaging Runtime Path

- Swift backend now starts in this order:
  1. bundled `netfix-backend` executable,
  2. bundled `Resources/python/bin/python3`,
  3. system `python3` for source/local builds.
- `build_app.sh` accepts `NETFIX_BACKEND_BIN=/path/to/netfix-backend` for standalone backend packaging.
- Added `scripts/build_backend_binary.sh` as a PyInstaller build entry for `dist/netfix-backend`; it supports `PYINSTALLER_PYTHON=/path/to/build-venv/bin/python` so build dependencies can stay outside the user Python environment.
- `netfix.constants` now resolves resources from `sys._MEIPASS` when running frozen.
- A real arm64 PyInstaller backend binary has been built and bundled into the local DMG candidate:
  - `dist/netfix-backend`,
  - `gui/macos/.build/Netfix.app/Contents/MacOS/netfix-backend`.
- `build_app.sh --release-candidate` creates a local DMG candidate at `gui/macos/.build/Netfix-0.2.0.dmg` and writes `release-manifest.json` into the bundle.
- If no runtime exists, the app now fails with an explicit runtime message instead of a vague backend launch failure.
- `NETFIX_REQUIRE_BUNDLED_RUNTIME=true` hard-fails packaging when neither `netfix-backend` nor bundled Python exists in the app bundle.
- `build_app.sh` now supports Developer ID signing and notarization when `NETFIX_SIGN_IDENTITY` plus `NETFIX_NOTARY_PROFILE` or Apple ID/team/password environment variables are provided.
- `release-manifest.json` now reflects actual bundled runtime files and no longer claims `notarized: true` just because notarization was requested. A successful notarized DMG build writes an external `.build/Netfix-0.2.0.notarization.json` receipt after `notarytool submit --wait` and `stapler staple` succeed.
- Added `scripts/release_gate.sh` to run provider contracts, Python syntax checks, marketing claims checks, full unittest, pytest, Swift build, release-candidate packaging, bundle audit, DMG verify, and DMG mount check.
- `scripts/release_gate.sh --with-backend-binary` builds `dist/netfix-backend`, requires a bundled runtime, packages it into the app, and verifies the DMG.
- Bundle packaging now copies `gui/web/index.html` into `Contents/Resources/gui/web/`, and bundle audit requires that file. This keeps the local Web console available for both standalone backend and source-fallback app runtime paths.
- Added `scripts/release_readiness.py` as a paid-release readiness summary. It aggregates workspace blockers, bundle audit, release manifest, bundled runtime, Developer ID signing, notarization, codesign verification, DMG verification, and manual release evidence gates for clean-machine QA, legal review, and live provider smoke. Blocker and warning checks now carry concrete `next_steps` commands, so the readiness report is actionable instead of a dead-end status. Local ad-hoc DMG candidates can pass release gate but still report `NOT READY` for paid external distribution until both technical and manual release blockers are resolved.
- Added `scripts/clean_machine_qa.py` to create, validate, and show `status` for structured clean-machine visual QA records. A clean-machine record must declare `result: pass`, pass each required app/Web/logs/AI/proxy/screenshot check, and reference at least two screenshot files. `template` can now prefill `app_version` from `release-manifest.json` and `dmg_sha256` from the tested DMG via `--manifest` and `--dmg`; `status` still leaves the human QA fields and checks pending until real clean-machine testing is done.
- Added `scripts/legal_release_review.py` to create, validate, and show `status` for structured legal/compliance review evidence. A legal record must declare `result: pass`, identify reviewer/date, pass privacy/EULA/app privacy/paid terms/residential-proxy-claims/LLM-provider-terms/no-bypass-claims checks, and reference reviewed privacy-policy and EULA artifacts. `template` can now prefill `privacy_policy_artifact` and `eula_artifact` from the bundled draft docs via `--privacy-policy` and `--eula`; `status` still leaves reviewer/date/result and every legal/compliance check pending until a qualified review is actually completed.
- Added `scripts/marketing_claims_check.py` to scan customer-facing README/docs/Web/macOS copy and enforce that product copy must avoid "clean residential IP", bypass-risk-control, anti-ban, and unsupported DeepSeek image/multimodal claims. It allows explicit safety boundaries such as DeepSeek remaining text-only and image-question routing to MiniMax/Kimi/Qwen instead of implying DeepSeek can answer screenshots.
- Added `scripts/release_evidence.py` to create, validate, and show `status` for `release-evidence.json` templates. Clean-machine QA evidence now requires a valid `netfix_clean_machine_qa.v1` record, legal review requires a valid local `netfix_legal_release_review.v1` record, and live provider smoke evidence requires a full live `provider_smoke_check.py --live --require-live --json` result, not fixture or skipped output. `template` can now prefill record paths for the three manual gates while keeping every gate flag false, so evidence wiring can be exported without claiming approval. `status` expands the three manual gates into current flag/record state and concrete next-step commands, without marking blockers as passed. `scripts/release_export.py --evidence-file ...` copies that evidence file plus referenced local record files and legal artifacts into the clean download export, and now generates `README-FIRST.md` with install, first-run, AI provider, customer proxy profile, and readiness-status guidance, so a future paid-ready package can carry auditable clean-machine QA, legal-review, and live-provider-smoke records instead of relying on verbal status. Export checksums, the returned `files` array, and `export-manifest.json` artifact keys now use export-relative POSIX paths such as `evidence/clean_machine_qa_record.json`, so nested evidence can be checked without path ambiguity. Clean-machine QA now explicitly gates customer proxy Profile lifecycle QA (`paste/import preview -> save-and-monitor -> replace credentials -> export -> delete and clear persisted monitor`) and domestic LLM setup testing (`DeepSeek text setup`, provider-scoped Keychain account selection, missing-key fallback, and MiniMax/Kimi/Qwen image-question routing copy).
- Added `scripts/verify_dmg_backend.sh`:
  - mounts the DMG,
  - verifies the mounted app manifest,
  - requires bundled runtime when `NETFIX_REQUIRE_BUNDLED_RUNTIME=true`,
  - starts the bundled `netfix-backend` from the mounted app,
  - checks `/health`, `/llm/providers`, `/proxy/monitor`, `/proxy/bridge`, and `/`,
  - verifies the Web console contains bridge lifecycle/startup-check renderers,
  - verifies bundled `/proxy/import-preview` returns `netfix_proxy_import_preview.v1` without provider-password echo,
  - verifies bundled `/proxy/profiles/<id>/replace` preserves the Profile id and rotates the endpoint before export,
  - verifies bundled `/proxy/profiles/<id>/export` returns `netfix_proxy_client_package.v1` with `README.md` and a sing-box file,
  - verifies bundled `/proxy/bridge` returns `netfix_proxy_bridge_lifecycle.v1` and `netfix_proxy_bridge_startup_check.v1`,
  - detaches the DMG with retry/force cleanup.
- `scripts/release_gate.sh --strict-workspace` is the source/repository release gate and intentionally fails while old proxy artifacts remain in the workspace.

### API/MCP

- Added HTTP endpoints:
  - `GET /logs`
  - `POST /logs/prune`
  - `POST /logs/clear`
  - `POST /data/clear`
  - `GET /llm/providers`
  - `GET /llm/chain-readiness`
  - `GET /settings/llm`
  - `POST /settings/llm`
  - `GET /settings/privacy`
  - `POST /settings/privacy`
  - `POST /llm/test`
  - `POST /llm/chain-test`
  - `POST /explain_llm`
  - `POST /proxy/parse`
  - `POST /proxy/validate`
  - `GET /proxy/validation-targets`
  - `GET/POST /proxy/profiles`
  - `POST /proxy/profiles/<id>/validate`
  - `GET /proxy/profiles/<id>/health`
  - `POST /proxy/profiles/<id>/apply-dry-run`
  - `POST /proxy/profiles/<id>/apply`
  - `POST /proxy/profiles/<id>/export`
  - `POST /proxy/profiles/rollback`
  - `GET /proxy/bridge`
  - `POST /proxy/bridge/recover`
  - `GET /proxy/monitor`
  - `POST /proxy/monitor/start`
  - `POST /proxy/monitor/stop`
- Added MCP tools:
  - `netfix_llm_providers`
  - `netfix_explain_llm`
  - `netfix_proxy_parse`
  - `netfix_proxy_import_preview`
- `netfix_llm_providers` now mirrors the local provider readiness cues used by the Web UI: `api_key_account`, `api_key_set`, `fallback_ready`, `text_explain_ready`, `image_question_provider_supported`, `image_question_adapter_ready`, `image_question_ready`, and `netfix_mode`.
- `netfix_explain_llm` now exposes `mode`, `upload_confirmed`, `allow_fallback`, and inline `images` inputs, so Agent/MCP hosts can use the same consent-gated image-question safety layer as Web/macOS. Images remain limited to inline PNG/JPEG/WebP/GIF data URLs and are still stripped/validated by `llm_explain.py`.
- MCP can parse, batch-preflight provider proxy lists, and explain; it cannot save API keys or proxy passwords, validate proxy credentials, or apply system proxy settings.

## Current Verification

- Full Python pytest suite passes: `330 passed`.
- Provider contract check passes: `scripts/provider_contract_check.py`; domestic provider presets now require official-doc evidence URLs, a 2026-06-25 metadata check date, MiniMax-M3 `max_completion_tokens` payload behavior, provider error redaction, and Chinese domestic provider error classification for rate-limit, quota/billing, auth, and model-missing failures.
- Provider fixture smoke passes: `scripts/provider_smoke_check.py`; fixture coverage is DeepSeek text plus Kimi/MiniMax/Qwen image-question parsing.
- Marketing claims check passes: `scripts/marketing_claims_check.py --json`; it scanned 28 customer-facing files with no findings.
- Targeted LLM safety tests pass for `/llm/chain-test` confirmation, disabled-AI no-call behavior, invalid-mode rejection without provider calls, `/llm/test` confirmation, provider error redaction, Chinese domestic provider error classification, provider-change `api_key_account` synchronization, local budget ledger persistence/clear/opt-out behavior, chain-readiness adapter evidence, Web cloud-AI enable toggle persistence plus provider-scoped `api_key_account`, Web chain-test/error/evidence rendering, Qwen-inclusive image-question copy, macOS native confirmation dialogs, macOS adapter-evidence decoding/rendering, and DMG static smoke coverage for the chain-test entrypoint.
- Targeted Web logs/proxy-save-monitor/release-audit/release-evidence/readiness/export run passes, including save-profile auto-monitor API/Web/macOS paths, replace-profile credential rotation API/Web/macOS paths, bulk-import candidate save-and-monitor UI coverage, single Profile delete/Keychain cleanup plus persisted-monitor cleanup, monitor repair-action `ui_action` rendering/buttons, authenticated SOCKS stale-bridge restart coverage, and clean-machine QA gate coverage for Profile lifecycle plus domestic LLM setup evidence.
- Swift App build passes: `swift build`.
- `swift test` is not currently usable in this local toolchain because `XCTest` is unavailable; model decode tests were added but need an XCTest-capable environment or CI runner.
- `scripts/release_gate.sh` passes end-to-end for the binary-app candidate path.
- `PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python ./scripts/release_gate.sh --with-backend-binary --skip-pytest` passes and produces a DMG whose manifest has `backend_runtime.bundled_backend: true` and `backend_runtime.bundled_runtime_required: true`.
- `scripts/verify_dmg_backend.sh` passes against `gui/macos/.build/Netfix-0.2.0.dmg`, proving the mounted DMG's bundled backend can serve core local API endpoints, the Web console homepage, `GET /llm/chain-readiness` with text/image chains, `GET /settings/proxy-bridge` with auto-restart defaulting to false, `POST /proxy/import-preview` without password echo, `POST /proxy/profiles/<id>/replace` preserving the Profile id while rotating the endpoint, `POST /proxy/profiles/<id>/export` with `netfix_proxy_client_package.v1`, and the proxy bridge lifecycle/startup-check contract.
- `scripts/release_export.py --skip-external --zip --json` exports a clean binary download folder and zip at `gui/macos/.build/release-export/Netfix-0.2.0-macos`; it includes `README-FIRST.md` plus pending `release-evidence.json` and referenced local evidence skeleton files, excludes the 14 source-workspace proxy artifact findings, and marks `paid_release_ready: false`. The exported binary-only readiness file reports 5 blockers because source-workspace artifacts are excluded from that package.
- `scripts/release_readiness.py --skip-external --json` run from the source workspace reports `NOT READY` with 6 blockers and per-blocker `next_steps`: source workspace audit blockers, Developer ID signing, notarization/stapling, clean-machine QA evidence, legal review/published policy evidence, and live provider smoke evidence.
- `scripts/clean_machine_qa.py status gui/macos/.build/clean-machine-qa.json --json` reports the prefilled clean-machine record, 0/12 checks passed, 2/6 fields complete, and keeps tester/machine/screenshots/result plus real clean-machine checks pending before validate can pass.
- `scripts/legal_release_review.py status gui/macos/.build/legal-release-review.json --json` reports the prefilled legal review record, 0/7 checks passed, 2/5 fields complete, and keeps reviewer/reviewed_at/result plus every legal/compliance check pending before validate can pass.
- `scripts/release_evidence.py status gui/macos/.build/release-evidence.json --json` reports 0 complete and 3 incomplete manual gates, with record paths prefilled but all flags false; next-step commands still require real clean-machine QA, legal review, and live provider smoke before any gate can pass.
- `scripts/provider_smoke_check.py status --json` reports provider key readiness without reading secrets; current local state has 0/4 provider keys ready and no live record, so live provider smoke remains a release blocker.
- Latest local DMG SHA-256: `be6c3a5375769e1b4eadb9bbb60e553fcfadd1beef27c9d51fece3b79196ad74`.
- Latest clean export ZIP SHA-256: `d69144dc9c50b49d55ef5393cd840ccc21f71461b95a9403568a78111e638547`.
- Latest bundled backend SHA-256: `9a78f90271b3c58580076826d6b7149ba40fa5da54bd3e5ef56db973ecac3f76`.
- Bundled backend smoke passes:
  - `netfix-backend --version` returns `netfix 0.2.0`,
  - bundled `netfix-backend server` serves `/health`, `/llm/providers`, `/llm/chain-readiness`, `/proxy/monitor`, and `/`,
  - Ctrl-C shutdown exits without traceback.
- Local release candidate packaging has passed in this sprint:
  - `build_app.sh --release-candidate`,
  - bundle `release_audit`,
  - `hdiutil verify`,
  - DMG mount check with `Netfix.app` at the volume root.
- New tests cover:
  - redaction,
  - residential proxy parsing,
  - residential proxy validation,
  - residential proxy apply confirmation,
  - local loopback proxy bridge auth injection,
  - local loopback HTTP bridge to authenticated SOCKS5 upstream without returning the upstream password,
  - residential proxy system apply command planning with mocked `networksetup`,
  - authenticated SOCKS system apply through a local bridge with mocked `networksetup`, Keychain password read, validation, journal write, and no SOCKS password in system commands,
  - residential proxy rollback confirmation and restore path,
  - residential proxy rollback bridge shutdown,
  - residential proxy validation target allowlist,
  - residential proxy validation target profiles (`baseline`, `ai_dev`) with MiniMax included,
  - top-level failure when non-baseline validation matrices hard-fail or return unexpected target HTTP results,
  - API/Web/macOS propagation of `target_profile` through manual validation, saved-profile validation, system apply verification, and proxy monitor persistence,
  - Web/macOS "验证有风险" rendering for identity/report warnings instead of calling warn states a clean pass,
  - domestic LLM provider order,
  - non-secret domestic LLM text/image chain readiness endpoint and Web/macOS rendering,
  - explicit domestic LLM chain-test confirmation and no-call behavior while AI is disabled,
  - invalid domestic LLM chain-test mode rejection before any provider or Keychain call,
  - persistent local LLM budget ledger pruning, restart survival, empty-status no-write behavior, explicit clearing via `/data/clear`, and automatic clearing when budget persistence is disabled,
  - single-provider LLM test confirmation and no-call behavior while AI is disabled,
  - provider error detail redaction before local API/UI output,
  - Web/macOS missing-key guided provider selection for domestic LLM chain setup,
  - DMG bundled-backend smoke coverage for `netfix_llm_chain_readiness.v1`,
  - provider contract checks,
  - OpenAI-compatible JSON response parsing,
  - fenced/embedded JSON response parsing,
  - provider output redaction,
  - provider URL compatibility,
  - `ask_each_time` upload consent enforcement,
  - `never` upload consent enforcement,
  - image-question metadata stripping and local audit summary,
  - fail-closed image data URL parsing for case variants, MIME mismatches, and malformed PNGs,
  - WebP EXIF/XMP/ICC and GIF comment/application/plain-text metadata stripping,
  - Web/macOS image-question visible-secret warning copy,
  - provider-scoped temporary LLM env keys,
  - sensitive local API token enforcement,
  - Web HttpOnly cookie auth without inline token injection,
  - removal of the public `/session` token endpoint,
  - Keychain secret write via stdin rather than argv,
  - destructive full local data and Keychain cleanup,
  - domestic provider fallback chain and failure reason codes,
  - provider registry capability contracts,
  - LLM fallback,
  - LLM action sanitization,
  - HTTP API new endpoints,
  - `/run rollback` acceptance for the macOS undo button,
  - log clearing,
  - event-log pruning,
  - latest-report privacy toggle,
  - Web diagnosis/fix failure recovery panel and DMG smoke coverage,
  - DMG bundled-backend smoke verification for `/proxy/import-preview` without provider-password echo,
  - browser token/Origin safety,
  - release audit,
  - structured clean-machine QA record validation,
  - clean-machine QA template prefill from release manifest and DMG SHA,
  - clean-machine QA status/next-step command reporting,
  - legal release review template prefill from privacy policy and EULA drafts,
  - live provider smoke evidence validation,
  - live provider smoke status/key-readiness reporting without provider calls,
  - release evidence template/validation,
  - release evidence status/next-step command reporting,
  - release evidence pending record-path prefill without passing gates,
  - release readiness blocker/warning next-step command reporting,
  - legal release review status/next-step command reporting,
  - release export copying evidence JSON and local evidence records,
  - release export first-run README generation and checksums,
  - manual release gates requiring record files/URLs rather than boolean flags alone,
  - marketing claims gate for residential-proxy claims and DeepSeek text-only/image-question boundaries,
  - proxy monitor,
  - residential proxy multi-line import preview without secret echo,
  - macOS Settings residential proxy multi-line import preview and candidate selection,
  - opt-in startup bridge restart without system proxy writes,
  - Web/macOS proxy bridge auto-restart settings controls,
  - MCP residential proxy multi-line import preview without secret echo,
  - first-class residential proxy client-package export without Keychain secret echo,
  - API/Web/macOS proxy monitor controls,
  - MCP safe proxy parsing,
  - DMG bundled-backend smoke verification for `netfix_proxy_client_package.v1` export with README and sing-box file,
  - DMG bundled-backend smoke verification for proxy bridge lifecycle/startup-check contracts,
  - residential proxy deployment-decision support matrix,
  - Web proxy operation rendering without raw JSON fallback,
  - macOS proxy deployment-decision decoding and display.
  - proxy bridge lifecycle summary states,
  - Web/macOS proxy bridge lifecycle display,
  - macOS rollback/recovery bridge-stop detail decoding.
  - startup stale-bridge check eventing and Web/macOS display.
  - macOS quit guard for running/stale bridge system proxy states.
  - opt-in startup restart of stale loopback bridge without system proxy writes, plus Web/macOS settings controls.
  - macOS menu bar bridge status refresh without system proxy writes,
  - macOS menu bar bridge attention status/notification copy for recovery-needed, check-failed, running-system, and auto-restarted states,
  - macOS notification toggle enforcement for bridge, health-status, and autofix notifications,
  - cancellable async `/run` jobs plus macOS Dashboard async diagnosis/service-check polling and cancellation.

## Remaining Release Blockers

P0 before paid external release:

1. Remove/rotate any real proxy config package from source/repository release inputs.
2. Provide Apple Developer ID and notary credentials, then run the existing signing/notarization path and clean-machine install test.
3. Run real clean-machine install/visual QA for the macOS App and Web console. DMG-mounted backend smoke now passes locally, but signed first-launch behavior and UI rendering on a clean Mac remain unverified.
4. Legal-review and publish privacy policy/EULA; drafts exist, App Store privacy labels still need final mapping. First-launch data/permission disclosure now exists in the app.
5. Run real provider sandbox-key smoke for DeepSeek/Kimi/MiniMax/Qwen before claiming vendor-live verification. Recorded fixtures now cover the response parsing and image-question schema path, but they do not prove current vendor availability, account entitlement, or billing state.

P1 after candidate:

1. Persist bridge lifecycle across app/backend restarts:
   - stale bridge detection and explicit restore now exist,
   - optional bridge restart on backend launch now exists after user opt-in and only restarts the local loopback bridge without changing system proxy,
   - menu bar now exposes a read-only bridge status line, status-dot override, and optional notification copy for recovery-needed/check-failed/auto-restarted states; remaining polish is clean-machine visual QA of these states.
2. Authenticated SOCKS upstream bridge support now exists for macOS Web/Secure Web proxy traffic through the local bridge; remaining work is clean-machine visual QA and real residential-provider pressure testing.
3. Extend residential proxy probes beyond the new conservative identity report:
   - verified DNS leak service instead of heuristic SOCKS/HTTP labels,
   - verified IPv6 fallback test after a confirmed system apply,
   - additional customer-workflow matrices beyond the current `baseline` and `ai_dev` allowlisted profiles.
4. Public screenshot/image question workflow:
   - backend supports consent-gated inline `data:image/...` inputs behind the `image_question` feature flag,
   - macOS and Web now have manual image selection, preview, and explicit upload confirmation,
   - image file metadata stripping and UX expectations are implemented; pixel/OCR redaction is not claimed and still needs real visual QA before marketing screenshot-safe automation,
   - MiniMax routes first, Kimi second, Qwen third; DeepSeek remains text-only.
6. Async progress and cancellation surfaced in SwiftUI for read-only diagnosis/service checks; mutating fix/rollback still use confirmed synchronous calls.
7. Private beta case capture and paid willingness test.
8. Persistent monitor launch polish:
   - auto-restore now happens only after the user explicitly starts monitoring,
   - still need persistent menu bar state and optional notification copy for restored monitoring,
   - continue avoiding hidden network activity when the user has not enabled monitoring.
9. Domestic LLM productization beyond the adapter layer:
   - live sandbox-key smoke for DeepSeek/Kimi/MiniMax/Qwen is still missing,
   - chain readiness now shows text/image provider gaps without live calls, can switch missing-key rows into the provider-key setup form, and has an explicit user-triggered live chain test; real provider-key evidence is still missing,
   - current budget/cooldown is local ledger governance, not a provider-billing hard limit or paid-license cost control.

## Acceptance Scenarios

The release candidate is not done until these work end-to-end:

1. User opens Netfix.app and sees engine state, not a silent failure.
2. User clicks "check AI/dev tools" and gets a root cause within 30-60 seconds.
3. If the log/report is empty, the UI says so; if present, the UI shows recent report and events.
4. Tier 1 fix can run and verify; Tier 2 only previews and asks confirmation.
5. User can explicitly enable/disable cloud AI and configure DeepSeek/Kimi/MiniMax/Qwen without the key appearing in settings or logs.
6. User can paste a residential proxy string or provider list in the macOS App or Web console, see a clear deployment support decision, save a chosen candidate without storing plaintext password in JSON, start background health monitoring from that save action, update/rotate an existing Profile's credentials when the provider issues a new host/port/user/password, validate it, start/stop background health monitoring later, delete one Profile with Keychain cleanup, click safe repair suggestions when monitoring fails, export a README-backed client configuration package, preview apply steps, confirm no-auth or authenticated HTTP/HTTPS/SOCKS system apply through the local bridge when credentials are needed, and rollback the last Netfix system apply.
7. Reports sent to LLM contain no proxy password, API key, subscription URL, raw stdout/stderr, hostname, full public IP, or provider endpoint host.
8. A clean Mac without Python either runs because runtime is bundled or gets an honest installer/runtime message. Current local DMG manifest and mounted-app smoke prove the bundled backend path; a separate clean-Mac install run is still required before external release.
