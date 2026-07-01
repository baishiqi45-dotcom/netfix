# GitHub Launch Guide

Stars follow usefulness, not promotion. This file keeps the repository honest, and gives the project a concrete playbook for the moment strangers land on the README.

## First Screen Promise

- The README first screen answers four questions in under five seconds:
  1. **What is it?** A local-first macOS network triage tool for AI / dev tools.
  2. **What does it do?** Tells you *which layer* broke (DNS, system proxy, proxy core, IPv6, TLS, target service, or your pasted credentials) before you change anything.
  3. **How do I install it?** Two one-line commands (App and MCP) are visible above the fold.
  4. **Is it different from what I already use?** A short comparison table is the first thing under the install buttons.

If any of those four answers is missing or buried below the fold, fix the README before asking for stars.

## Repository Metadata

Suggested description (already in `.github/repository.yml`):

```text
Local-first macOS network triage for AI/dev tools: diagnose DNS, proxy, node, IPv6, TLS, and target service issues before changing config.
```

Topics are intentionally tuned for 2026 search traffic: `macos`, `apple-silicon`, `swiftui`, `network-diagnostics`, `codex`, `claude`, `cursor`, `kimi`, `mcp`, `model-context-protocol`, `clash`, `mihomo`, `sing-box`.

## Comparison Snippet (paste into README)

| Tool | What it is | What Netfix adds |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | Client apps for an already-working proxy. You bring the proxy, they route traffic. | Netfix tells you *whether the proxy can even exist* on your Mac right now, and rolls back if applying it breaks the network. |
| **Activity Monitor / `netstat`** | Generic process and port inspection. | Layer-aware diagnosis: it distinguishes DNS, system proxy, proxy core, IPv6, TLS, and target service in one report. |
| **Random `curl` / `ping` from a chatbot** | Manual probes the model improvises. | Structured JSON output, tiered fixes with confirmation, automatic rollback, sanitized redaction before any optional cloud AI call. |
| **iStat Menus / network monitoring widgets** | Live throughput / signal display. | Recovery-oriented: paste a proxy, precheck it, deploy it, monitor it, restore the original network. |

## Social Proof — what to add before the public push

- [ ] At least 6 real screenshots of the Mac app under `assets/github/zh/` and `assets/github/en/`, all on a sanitized demo profile (no real desktop, no real hosts, masked passwords).
- [ ] One 8-second GIF of `python3 netfix.py codex --json` running on a synthetic failure.
- [ ] One short GIF of the in-app "restore original network settings" prompt.
- [ ] At least one sanitized case from `cases/` linked from the README "Real cases" section.

## Cases Worth Linking From The README

These exist already and are ready to be quoted (each must be sanitized before linking):

- `cases/20260617-1405-codex-reachable-needs-key.md` — "Codex 网络通但 API Key 失效" 的经典场景。
- `cases/2026-06-17-healthy-baseline.md` — 健康基线作为 before/after 对照。
- `cases/2026-06-29-普通用户代理部署体验审查.md` — 普通用户视角的痛点，最适合做 "Real user story" 引流。
- `cases/TEMPLATE.md` — 模板，提醒贡献者如何脱敏。

## Launch Copy (people, not just CI)

Short Chinese copy:

```text
macOS 上 Codex / ChatGPT / GitHub 突然连不上时，Netfix 先告诉你卡在哪一层：
DNS、系统代理、代理核心、IPv6、TLS、目标服务，还是你粘贴的代理参数本身。
不需要 API Key 也能用，需要时也只是把脱敏后的诊断发到云端。
```

Short English copy:

```text
Netfix tells you which layer broke when Codex, ChatGPT, GitHub, or your
API client stops connecting — DNS, system proxy, proxy core, IPv6, TLS,
or the saved proxy credentials themselves. Open the Mac app, click once,
get a plain-English answer. Local-first, no telemetry, no cloud required.
```

## Trust Claims — safe to assert

- local-first diagnosis (works offline)
- optional AI explanation after on-device redaction
- proxy credentials stored in macOS Keychain only
- every config-changing fix requires explicit user confirmation
- backup-and-rollback for system network changes
- MIT license
- source-first: build from `git clone` and `pip install .`

## Claims — must NOT appear

- Netfix never claims guaranteed connectivity or guaranteed residential IP, and the docs must not promise any kind of third-party rule circumvention.
- No "DeepSeek 支持图片" / "DeepSeek is a vision model" — DeepSeek is text-only in this codebase.
- No "signed and notarized public DMG" before `release_preflight --with-dmg-smoke` actually passes Developer ID signing and notarization.
- No case quoting a real proxy URL, API key, QR code, cookie, or bearer token.

## How To Ask For Stars Without Begging

1. After the README change above, post the release on:
   - Hacker News (`Show HN`) with a one-paragraph problem statement, not a feature list.
   - r/macapps, r/MacOS, r/Proxifier (avoid rules-violating subs).
   - V2EX, NodeSeek, InfoQ CN — for the Chinese audience, with the Chinese README.
2. In every post, link to a **single concrete case** (`cases/2026-06-29-普通用户代理部署体验审查.md` is currently the strongest hook).
3. Do not promise what is not in the release. The current QA DMG is unsigned; say so out loud — credibility earns stars more than polish.
4. After 30 stars, write a follow-up post showing the **before / after** of a real diagnosis.

## Before Asking For Stars — verification

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke --json
python3 scripts/marketing_claims_check.py --json
```

Then manually check:

- README first screen renders both badges and hero image.
- README.en.md has no `<repo>` placeholder and the comparison table is above the fold.
- The one-line Codex MCP install works from a clean account through the raw `main` installer:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash`
- The one-line macOS app install works through the raw `main` installer, which downloads the `v0.2.0-qa.1` QA DMG:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash`
- GitHub Issues have safe templates and PR template covers architecture / schema impact.
- SECURITY.md gives a private-report path or a sanitized fallback.
- Release notes do not call an unsigned local build a public product.
