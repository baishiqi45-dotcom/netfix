# Netfix

[中文 README](README.md)

![Netfix local-first macOS network rescue kit](assets/github/hero.en.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: local first](https://img.shields.io/badge/privacy-local--first-0f766e)
![agent: MCP ready](https://img.shields.io/badge/agent-MCP%20ready-111827)

Netfix is a local-first macOS network triage tool for AI and developer workflows. When Codex, ChatGPT, GitHub, or an API client stops connecting, Netfix checks DNS, system proxy, proxy cores, IPv6, TLS, and target services before asking you to try random commands.

The product goal is a desktop app that a non-terminal user can open, run, and recover from: diagnose locally, explain in plain language, apply fixes only after confirmation, and restore the original network settings when needed.

## What It Solves

- AI and developer tools stop connecting, and the user cannot tell whether DNS, proxy, TLS, or the target service failed.
- A user has legal proxy credentials such as `host:port:user:pass` but does not know how to precheck and apply them on macOS.
- A route works intermittently, and the user needs exit, reachability, IPv6, and TLS checks instead of guesses.
- Codex, Kimi, Claude, or another agent needs structured diagnostics instead of hand-written shell probes.
- The user does not want proxy passwords, API keys, or raw reports uploaded to a cloud service.

## Current Use

This repository is ready for source-first open-source review and local execution. A public signed `.dmg` is not ready yet because Developer ID signing and notarization are still missing. Do not market the local candidate build as an official external download.

One-line Codex MCP install for other users, after this repository has been pushed publicly to GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

The command downloads source to `~/.netfix/netfix-codex-mcp-source`, runs an MCP initialization check, and registers `codex mcp add netfix -- python3 .../netfix/mcp_server.py`. Restart Codex or open a new Codex thread afterwards. It does not copy proxy passwords or API keys.

One-line local macOS app install, after a signed and notarized `Netfix-0.2.0.dmg` has been published to GitHub Releases:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash
```

The command downloads the DMG, installs `Netfix.app` to `~/Applications`, registers Netfix MCP for Codex when the Codex CLI exists, and opens the app. The current local DMG is not Developer ID signed or notarized, so it should not be presented as a finished non-technical installer yet.

From a source checkout:

```bash
python3 netfix.py codex
python3 netfix.py codex --json
python3 netfix.py server --host 127.0.0.1 --port 8765
```

The third command starts the local Web dashboard at `http://127.0.0.1:8765/`. Do not open `gui/web/index.html` directly through `file://`; that page has no backend.

Build the local macOS app:

```bash
cd gui/macos
swift build
./build_app.sh
open .build/Netfix.app
```

The intended user entry is `Netfix.app`: double-click, let the app start the local engine, and use the UI instead of a terminal.

![Netfix user path](assets/github/workflow.en.png)

## What To Paste For Proxy Setup

Do not paste the current exit IP from an IP lookup page. That is only a result, not a connection string.

Paste the connection parameters from a proxy service you legally own or operate. Netfix accepts common forms:

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

In the app, open Settings -> Proxy, paste the parameters, run Precheck, then save them to this Mac. To route system apps through the saved profile, click Deploy to this Mac. Authenticated HTTP/HTTPS/SOCKS proxies are bridged locally by Netfix; passwords go to macOS Keychain and are not written to shell history, logs, reports, screenshots, or release packages. Netfix backs up the original network settings before applying changes so you can restore them.

Boundary: Netfix does not sell proxies, ship built-in nodes, promise provider quality, promise clean residential IP outcomes, or help bypass third-party account, risk, or abuse controls. It only parses, prechecks, stores, deploys, monitors, and restores credentials the user already has.

## Optional AI Explanation

Netfix works without an AI API key. Local rules produce the first explanation. If you configure a provider, the cloud model only explains a redacted report.

App path: Settings -> AI, choose DeepSeek, Kimi/Moonshot, MiniMax, Qwen, or a custom OpenAI-compatible provider, then save the key to Keychain.

Environment variable path:

```bash
export NETFIX_LLM_API_KEY_DEEPSEEK="sk-..."
python3 netfix.py explain --provider deepseek --json
```

DeepSeek is the default text explanation provider. Image question flows route to MiniMax, Kimi/Moonshot, or Qwen after explicit upload confirmation. Do not describe DeepSeek as a vision or screenshot model.

## Connect Codex / Kimi

Users who installed the app should not hunt for repository scripts:

1. Open Netfix.
2. Go to Settings -> Agent -> Copy for Codex, paste the command into a Codex terminal, then restart Codex.
3. For Kimi, use Copy Kimi / generic config. Some current Kimi Code CLI versions do not expose `mcp add`; do not paste old commands. Use the generic stdio config in a Kimi/Agent host that supports MCP.

Source checkout users can register Codex and detect Kimi support from the repository root:

```bash
./scripts/install_mcp.sh --all
./scripts/install_mcp.sh --all --dry-run
```

Manual Codex registration:

```bash
codex mcp add netfix -- python3 "$(pwd)/netfix/mcp_server.py"
codex mcp list
```

Kimi / generic MCP stdio config:

```yaml
name: netfix
command: python3
args:
  - /absolute/path/to/netfix/mcp_server.py
```

The standard agent entry is:

```bash
python3 netfix.py codex --json
```

Agents should read `environment.active_profile`, `diagnostics`, `root_causes`, `fixes`, and `manual_steps`. Low-risk fixes may run directly. Any config-changing action must ask the user first. Manual-only steps should stay as checklists.

## Features

| Capability | User view | Developer surface |
|---|---|---|
| One-click diagnosis | Shows the failed layer and next step | `python3 netfix.py codex --json` |
| Proxy paste deploy | Paste, precheck, save, deploy, restore | `proxy`, `proxy-monitor`, `proxy-switch` |
| AI explanation | Optional cloud explanation after redaction | Local HTTP API / MCP |
| Health maintenance | Route, IPv6, TLS, DNS, and service hints | `watch`, `report`, `logs` |
| Agent integration | Copy Codex / Kimi registration commands | `netfix/mcp_server.py` |
| Rollback | Backup before config changes | `fix`, `rollback`, journal |

## Safety Model

- Local-first diagnosis and rule reasoning do not require an external LLM.
- Low-risk fixes can run directly; config-changing fixes require explicit user confirmation.
- Proxy passwords and API keys must not appear in reports, screenshots, logs, export packages, or GitHub Issues.
- Image uploads are explicit; Netfix cannot automatically redact visible text inside image pixels.
- Netfix is not a proxy provider and does not promise third-party service availability.

## Open-Source Release State

Use `scripts/source_export.py` to create a clean source snapshot before publication. It excludes old proxy credential packages, generated DMG/ZIP files, build outputs, and local runtime state. Publish `open-source-export/Netfix-0.2.0-source` rather than a private development workspace.

Verification:

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke
```

If `release_audit` reports `tracked-release-artifact`, remove release artifacts from the git index without deleting local files:

```bash
git ls-files 'Netfix-*.dmg' 'Netfix-*.zip'
git rm --cached Netfix-0.2.0.dmg Netfix-0.2.0-macos.zip
python3 scripts/release_audit.py --scope workspace --root .
```

External binary distribution still requires Developer ID signing, notarization, clean-machine QA, legal review, and live provider smoke evidence.

## Repository Map

```text
netfix/
├── netfix.py              CLI entry
├── netfix/                diagnosis, reasoning, fixes, API, MCP
├── gui/macos/             SwiftUI local app
├── gui/web/               local Web dashboard
├── rules/                 services, symptoms, root-cause rules
├── scripts/               release, audit, MCP installer scripts
├── tests/                 Python / API / MCP / UI text tests
├── assets/github/         Chinese and English GitHub visuals
└── docs/github/           GitHub release and screenshot notes
```

## License

MIT
