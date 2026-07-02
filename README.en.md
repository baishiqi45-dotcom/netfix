# Netfix

[中文 README](README.md)

![Netfix local-first macOS network rescue kit](assets/github/hero.en.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: local first](https://img.shields.io/badge/privacy-local--first-0f766e)
![agent: MCP ready](https://img.shields.io/badge/agent-MCP%20ready-111827)

## What it does

Got legal proxy credentials but do not know how to configure your Mac? Netfix lets you paste one complete proxy line, precheck it, save it locally, and only then confirm whether this Mac should start using it.

When Codex, ChatGPT, GitHub, or any API client suddenly stops connecting, **Netfix also tells you which layer broke**:
DNS, system proxy, proxy core (xray / sing-box / mihomo / Clash), IPv6, TLS, the target service — or the proxy parameters you pasted yourself.
It only changes network settings after you confirm, and it backs up your original config so you can roll back with one click.
No API key is required. If you do configure one, the model only ever sees an on-device-redacted version of the diagnostic.

## Get started in 60 seconds

> ⚠️ The current DMG is the **v0.2.0-qa.1 preview build, unsigned and not notarized**. On first launch, macOS will block it; open System Settings → Privacy & Security → Open Anyway. Do not market this QA build as an official external release.

```bash
# Most users copy this line: install Netfix.app (QA build, unsigned; first launch: System Settings → Privacy & Security → Open Anyway)
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

# Preview installer actions without installing
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --dry-run

# Uninstall the local app and Codex MCP registration
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash -s -- --uninstall

# Developer / Agent users: one-line Codex MCP registration. Kimi / Claude / Cursor use the manual config below.
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

From source:

```bash
pip install -e .
python3 netfix.py codex --json
```

## How this differs

| Tool | What it is | What Netfix adds |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | Client apps for an already-working proxy. You bring the node, they route traffic. | Netfix tells you *whether the proxy can exist* on your Mac right now, prechecks before applying, and rolls back if it breaks. |
| **Activity Monitor / `netstat`** | Generic process and port inspection. | One report covers DNS, system proxy, proxy core, IPv6, TLS, and target service in parallel and labels the failed layer. |
| **Random `curl` / `ping` from a chatbot** | Manual probes the model improvises. | Structured JSON, tiered fixes with confirmation, automatic rollback, and mandatory redaction before any optional cloud call. |
| **Network monitoring widgets** | Live throughput / signal display. | Recovery-oriented: paste → precheck → deploy → monitor → restore. |

## What it does NOT do

- **No proxy selling. No built-in nodes. No promises about third-party quality.** Netfix only parses, prechecks, stores, deploys, monitors, and restores credentials **you already have**.
- **Strict compliance with third-party platform account, risk-control, geo, and abuse rules; no circumvention.**
- **No** automatic leak of your proxy passwords, API keys, raw reports, QR codes, or cookies to the cloud, shell history, screenshots, or GitHub Issues.

## Current Use

This repository is ready for source-first open-source review and local execution. A public signed `.dmg` is not ready yet because Developer ID signing and notarization are still missing. Do not market the local candidate build as an official external download.

One-line Codex MCP install for other users. This downloads the installer from `main`, and the installer downloads `main` source by default. Use `NETFIX_REF` / `NETFIX_REF_KIND=tags` if you want to pin a release tag:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash
```

The command downloads source to `~/.netfix/netfix-codex-mcp-source`, runs an MCP initialization check, and registers `codex mcp add netfix -- python3 .../netfix/mcp_server.py`. Restart Codex or open a new Codex thread afterwards. It does not copy proxy passwords or API keys.

One-line local macOS app install. This downloads the installer from `main`; the installer currently downloads the unsigned QA DMG from `v0.2.0-qa.1`:

```bash
curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash
```

The command downloads the DMG, verifies SHA256, installs `Netfix.app` to `~/Applications`, registers Netfix MCP for Codex when the Codex CLI exists, and opens the app. The current QA DMG is not Developer ID signed or notarized, so it is suitable for technical testers, not finished non-technical distribution.

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

## Real cases

`cases/` holds sanitized real scenarios. A few worth quoting in the README:

- **"Codex reports unreachable — turns out the API key expired"** — `cases/20260617-1405-codex-reachable-needs-key.md`. The network was fine; Netfix points away from the wrong suspect.
- **"9 pitfalls for a non-technical user deploying their first proxy"** — `cases/2026-06-29-普通用户代理部署体验审查.md`. Paste → precheck → deploy → rollback, in plain language.
- **"Healthy baseline snapshot"** — `cases/2026-06-17-healthy-baseline.md`. Before/after comparison for fast triage next time.

New cases welcome. Use `cases/TEMPLATE.md`, read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before opening a PR.

## What To Paste For Proxy Setup

Do not paste the current exit IP from an IP lookup page. That is only a result, not a connection string.

Paste the connection parameters from a proxy service you legally own or operate. Netfix accepts common forms:

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

In the app, open Settings -> Proxy, paste the parameters, click Check whether this line works, then save them to this Mac. To route system apps through the saved profile, click Start using this proxy on this Mac. Authenticated HTTP/HTTPS/SOCKS proxies are bridged locally by Netfix; passwords go to macOS Keychain and are not written to shell history, logs, reports, screenshots, or release packages. Netfix backs up the original network settings before applying changes so you can restore them.

Boundary: Netfix does not sell proxies, ship built-in nodes, promise provider quality, promise any specific exit quality, or help bypass third-party account, risk, geo, or abuse controls. It only parses, prechecks, stores, deploys, monitors, and restores credentials the user already has.

## FAQ

**Can I use it without an API key?**
Yes. Diagnosis, local rule explanations, proxy precheck, save, apply, and restore work locally. API keys are only used when you explicitly enable optional cloud AI explanation.

**Can it break my network?**
Netfix backs up your previous system proxy settings before applying changes. Click Restore original network settings when you want to stop using the proxy.

**Where are proxy passwords and API keys stored?**
Only in macOS Keychain. They are not written to logs, reports, screenshots, release packages, or GitHub Issues.

**Which proxy formats are supported?**
`host:port:user:pass`, `http://user:pass@host:port`, `socks5://user:pass@host:port`, and `host,port,user,pass`. `ss://`, `vmess://`, and Clash/sing-box subscription links are not supported yet.

## Optional AI Explanation

Netfix works without an AI API key. Local rules produce the first explanation. If you configure a provider, the cloud model only explains a redacted report.

App path: Settings -> AI, choose DeepSeek, Kimi/Moonshot, MiniMax, Qwen, or a custom OpenAI-compatible provider, then save the key to Keychain.

Environment variable path:

```bash
export NETFIX_LLM_API_KEY_DEEPSEEK="sk-..."
python3 netfix.py explain --provider deepseek --json
```

DeepSeek is the default text explanation provider. Image question flows route to MiniMax, Kimi/Moonshot, or Qwen after explicit upload confirmation. Do not describe DeepSeek as a vision or screenshot model.

## Connect Codex / Kimi / Claude / Cursor

Users who installed the app should not hunt for repository scripts:

1. Open Netfix.
2. Go to Settings -> AI Coding Assistant -> Copy for Codex, paste the command into a Codex terminal, then restart Codex.
3. For Kimi, use Copy Kimi / generic config. Some current Kimi Code CLI versions do not expose `mcp add`; do not paste old commands. Use the generic stdio config in a Kimi/Agent host that supports MCP.
4. For Claude Desktop / Cursor, copy the `mcp.json` snippet from the app and paste it into the matching MCP config file (paths are in [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md)).

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

Kimi / Claude / Cursor MCP stdio config:

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
| Agent integration | Copy Codex / Kimi / Claude / Cursor registration commands | `netfix/mcp_server.py` |
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
