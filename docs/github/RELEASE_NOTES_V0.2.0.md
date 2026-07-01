# Netfix v0.2.0 Release Notes Draft

Netfix v0.2.0 focuses on the source-first open-source release and local macOS product path.

## Highlights

- One-click local diagnosis for Codex, ChatGPT, GitHub, proxy, DNS, IPv6, TLS, and target-service reachability.
- SwiftUI macOS app path for users who should not need a terminal.
- Proxy parameter paste flow for user-owned HTTP/HTTPS/SOCKS credentials.
- Local Keychain storage and rollback-oriented network setting changes.
- Optional AI explanation with redaction and provider-scoped keys.
- MCP server and installer script for Codex and Kimi.
- Clean source export pipeline for public GitHub release hygiene.

## Current Boundary

The source release is the publishable unit. A signed and notarized public `.dmg` is not ready until Developer ID signing, notarization, clean-machine QA, legal review, and live provider smoke checks are complete.

## Verify

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_preflight.py --with-dmg-smoke --json
```
