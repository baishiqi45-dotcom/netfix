# Netfix v0.2.0 — Release Notes

> **This is a source-first release.** The macOS DMG is a QA-only artifact: it is **not Developer ID signed** and **not notarized**. macOS will ask you to right-click → Open the first time. Do not redistribute the DMG as a public product yet.

## What changed for you

- **One-click diagnosis.** If Codex, ChatGPT, GitHub, or any API client suddenly stops connecting, click once and Netfix tells you which layer broke: DNS, system proxy, your proxy core (xray / sing-box / mihomo / Clash), IPv6, TLS, the target service, or the proxy parameters you pasted.
- **Plain-language explanations, even offline.** Local rule engine ships first. No API key required to read the answer.
- **Paste a proxy, deploy it, roll it back.** Paste `host:port:user:pass` or `socks5h://user:pass@host:port`. Netfix prechecks it, saves the password to macOS Keychain, deploys to system proxy only after you confirm, and backs up your original network settings so you can revert.
- **Optional AI explanation.** Add a DeepSeek / Kimi / MiniMax / Qwen / OpenAI-compatible key in *Settings → AI* and Netfix will rewrite the diagnostic in plain English after on-device redaction. Keychain only, never shell history or logs.
- **Agent-native.** Codex, Kimi, Claude Desktop, and Cursor can call Netfix through MCP. The server is local stdio; nothing leaves your Mac.
- **Source-first.** `pip install .` and you have the full CLI; `cd gui/macos && swift build && ./build_app.sh` and you have the Mac app. The whole codebase is MIT-licensed and audited before each public source export.

## Try it in 60 seconds

macOS App (QA DMG, unsigned):

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash
```

Codex MCP one-line registration:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

Kimi / Claude / Cursor / MiniMax-compatible local agents can use the generic MCP stdio config printed by the App installer, or copy it later from *Settings → AI Coding Assistant*. The installer only auto-registers Codex CLI when `codex` is available.

Source build:

```bash
pip install -e .
python3 netfix.py codex --json
```

## What is NOT in this release

- No signed / notarized `.dmg`. Public binary distribution requires Developer ID signing, Apple notarization, clean-machine QA, legal review, and live provider smoke checks. Until then, please do not call this a finished Mac app.
- No Linux / Windows support. Netfix shells out to macOS-only tooling (`scutil`, `networksetup`, `dscacheutil`, `security`).
- No built-in proxy providers, no node list, no account bypass tools. Netfix only parses, prechecks, stores, deploys, monitors, and restores credentials **you already have**.
- No automated image-text redaction inside screenshots. If you upload a screenshot to the optional AI, visible text in the image is on you to sanitize first.

## Proof you can check

- Real user story: [ordinary-user proxy deployment review](../../cases/2026-06-29-普通用户代理部署体验审查.md). This is the strongest explanation of why the product flow is paste → precheck → deploy → rollback.
- Installer dry run:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --dry-run
```

- Local CLI smoke:

```bash
python3 netfix.py codex --json
```

The output is structured JSON. Agents should read `diagnostics`, `root_causes`, `fixes`, and `manual_steps`; users should not paste raw reports with secrets into public issues.

## Known limits

- `python3 netfix.py codex --json` may take 30–60s on a cold run because it actually probes DNS, proxy cores, and target services in parallel.
- Proxy bridge only listens on IPv4 loopback. macOS LAN clients cannot reach it.
- One macOS network service is configured at a time. Multi-service / VPN / Bluetooth PAN IPv6 leak checks are best-effort.
- Default rule set covers AI APIs (OpenAI, Anthropic, DeepSeek, Moonshot, MiniMax, Qwen), GitHub, Apple, Google, and Cloudflare. New service requests welcome via `rules/services.json`.

## Verify before you trust it

```bash
python3 -m pytest -q
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke
```

If you find a regression, please file a [Bug report](../../.github/ISSUE_TEMPLATE/bug_report.md) — never paste live credentials, use the [safe diagnostic report](../../.github/ISSUE_TEMPLATE/safe_diagnostic_report.md) template instead.
