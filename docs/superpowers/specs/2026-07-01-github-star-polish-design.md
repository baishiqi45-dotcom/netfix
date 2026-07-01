# Netfix GitHub Star Polish Design

## Goal

Make Netfix understandable and attractive on GitHub within 30 seconds, while staying honest about its current release state. A visitor should know the pain point, see the product shape, understand how to try it, and trust that the project does not leak proxy credentials or overpromise "clean residential IP" outcomes.

## Target Visitor

- macOS developer or AI tool user whose Codex, ChatGPT, GitHub, or API access often breaks because of DNS, proxy, IPv6, or local client issues.
- Maintainer or agent-tool user who wants a local diagnostic tool with JSON/MCP output.
- Non-expert user who bought or owns proxy credentials and needs a local UI to paste, test, deploy, monitor, and restore safely.

## Positioning

Tagline: **"A local-first macOS network rescue kit for AI developers."**

Support copy:
- Diagnose Codex/OpenAI/GitHub connectivity without sending reports to a cloud service.
- Paste `host:port:user:pass` proxy credentials, test them, deploy them to this Mac, monitor health, and restore the previous network settings.
- Register Netfix as a Codex/Kimi MCP tool so agents can read structured diagnostics instead of guessing from ad hoc shell commands.

## Public Surface

1. `README.md`: primary GitHub landing page in Chinese, with concise English bridge.
2. `README.en.md`: real English landing page, not a thin technical note.
3. `assets/github/`: README-safe images:
   - `hero.svg`: product map and value proposition.
   - `workflow.svg`: one-click diagnose -> paste proxy -> deploy -> monitor -> restore.
4. `docs/github/`: supporting public docs:
   - `STAR_GUIDE.md`: what to star/watch/fork for and how to help.
   - `SCREENSHOTS.md`: visual tour and screenshot checklist.
5. `.github/`: templates and CI remain strict about secrets and generated binaries.

## README Structure

The first screen should show:
- Name, tagline, badges.
- One-sentence problem statement.
- Product screenshot/hero image.
- "What it fixes" bullets.
- "Try it in 3 minutes" path.
- Trust boundary: local-first, no bundled proxy nodes, optional cloud AI.

Move deep CLI/API details lower. Keep warnings honest but not dominant in the first 20 lines.

## Visual Direction

Use crisp technical product visuals, not vague marketing art:
- A dark macOS-style panel showing status, proxy deploy, and MCP/agent path.
- A workflow diagram with concrete states and labels.
- No claims of bypassing platforms, anti-ban, or guaranteed residential quality.

## Release Honesty

Current state should be presented as:
- Open-source source: ready.
- Local unsigned macOS candidate: usable for QA and local use.
- Paid external release: not ready until Developer ID signing, notarization, clean-machine QA, and live provider smoke are complete.

## Verification

Before calling this done:
- `python3 -m pytest -q`
- `python3 scripts/release_audit.py --scope workspace --root . --json`
- `python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source --json`
- `python3 scripts/release_preflight.py --skip-external --with-dmg-smoke --write-record gui/macos/.build/release-export/Netfix-0.2.0-macos/download-qa-preflight.json --json`
- README scans for old internal names, absolute local paths, or overclaiming residential proxy language.
