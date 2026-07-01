# GitHub Launch Guide

This file is the public-facing launch checklist for Netfix. It keeps the repository honest: the goal is more stars because the project is useful, understandable, and safe to try, not because the README overpromises.

## First Screen

- Chinese README uses `assets/github/hero.zh.png`.
- English README uses `assets/github/hero.en.png`.
- Both READMEs explain the same pain: AI/dev tools stop connecting, and Netfix finds the broken network layer locally.
- The first screen must not lead with unsigned DMG warnings, internal release blockers, or long CLI lists.

## Repository Metadata

Suggested description:

```text
Offline-first macOS network triage for AI/dev tools: diagnose DNS, proxy, node, TLS, and service issues locally.
```

Suggested topics are stored in `.github/repository.yml`.

## Launch Copy

Short Chinese copy:

```text
macOS 上 Codex / ChatGPT / GitHub 突然连不上时，Netfix 先告诉你卡在哪一层：DNS、系统代理、代理核心、IPv6、TLS、目标服务，还是代理参数本身。
```

Short English copy:

```text
Netfix is a local-first macOS network triage tool for AI and developer workflows.
```

## Trust Claims

Safe claims:

- local-first diagnosis
- optional AI explanation after redaction
- proxy credentials stored in Keychain
- config-changing fixes require confirmation
- rollback for changed network settings
- MIT license

Do not claim:

- Do not promise guaranteed service access.
- Do not promise clean residential IP outcomes.
- Do not promise account or risk-control bypass.
- Do not promise provider quality.
- Do not claim a signed/notarized binary release before it exists.

## Before Asking For Stars

Run:

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_preflight.py --with-dmg-smoke --json
```

Then manually check:

- README first screen renders both badges and hero image.
- README.en.md has no `<repo>` placeholder.
- The one-line Codex MCP install works from a clean account after the GitHub branch is pushed:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash`
- The one-line macOS app install works only after a signed/notarized DMG is published to GitHub Releases:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash`
- GitHub Issues have safe templates.
- SECURITY.md gives a private-report path or a sanitized fallback.
- Release notes do not call an unsigned local build a public product.
