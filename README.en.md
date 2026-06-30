# netfix

An offline-first macOS network self-rescue product for users who rely on overseas services (ChatGPT, Codex, GitHub, YouTube, etc.) behind a proxy/VPN.

> Goal: works without external LLMs or pip packages, and is usable by non-technical users.

## Product form

- **Menu bar app** (SwiftUI): one-click diagnosis / fix.
- **Web dashboard**: open in browser, no install needed beyond the backend.
- **CLI**: kept for power users and scripts.
- **MCP / local HTTP API**: callable by Kimi, Codex, Minimax and other agents.

Boundary: cloud AI explanation is optional and consent-gated. Image question uploads accept only PNG, JPEG, WebP, or GIF; Netfix strips supported image file metadata before provider calls, but it does not automatically detect or redact visible text, passwords, API keys, or account identifiers inside image pixels. Residential/custom proxy features help users parse, validate, monitor, and export configuration packages for credentials they already own; Netfix does not sell proxies or promise bypass, anti-ban, or "clean residential IP" outcomes.

## Quick start

```bash
git clone <repo>
cd netfix
python3 netfix.py server --host 127.0.0.1 --port 8765
# Open http://127.0.0.1:8765/ in your browser
```

Or use the CLI:

```bash
python3 netfix.py codex
python3 netfix.py codex --json
```

## Build the native menu bar app

```bash
cd gui/macos
swift build
./build_app.sh
open .build/Netfix.app
```

## Register as an MCP server (Kimi / Codex)

```bash
kimi mcp add netfix \
  --transport stdio \
  --command python3 \
  --args /path/to/netfix/mcp_server.py
```

## Architecture

```
netfix/
├── cli.py            CLI entry
├── service_runner.py CLI wrapper for API / MCP
├── api.py            Local HTTP API + web dashboard
├── mcp_server.py     MCP stdio server
├── services.py       Configurable overseas service catalog
├── i18n/             Chinese copy for human-readable reports
├── detect.py         Platform / proxy core detection
├── cores/            Adapters for v2rayN / mihomo / Clash / WireGuard
├── diagnose.py       Diagnostic dispatcher
├── reasoner.py       Rule-based root-cause inference
├── fix_engine.py     Tiered fixes with backup and rollback
├── safety.py         Safety tiers
├── report.py         Report generation
├── kb.py             Knowledge base
└── utils.py          Utilities
```

## Safety tiers

| Tier | Type | Behavior |
|---|---|---|
| 0 | Read-only diagnostics | Auto-run |
| 1 | Low-risk fixes (flush DNS cache) | Auto-run, `--dry-run` preview |
| 2 | Config-changing fixes | Backup + diff + user confirmation |
| 3 | Manual-only | Output checklist only |

## License

MIT
