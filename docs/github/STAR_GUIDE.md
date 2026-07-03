# GitHub Launch Guide

Stars follow usefulness, not promotion. This file keeps the repository honest, and gives the project a concrete playbook for the moment strangers land on the README.

## First Screen Promise

- The README first screen answers four questions in under five seconds:
  1. **What is it?** A local-first macOS network triage tool for AI / dev tools.
  2. **What does it do?** Tells you *which layer* broke (DNS, system proxy, proxy core, IPv6, TLS, target service, or your pasted credentials) before you change anything.
  3. **How do I try it safely?** `--dry-run` is visible before the unsigned QA App install command.
  4. **Is it different from what I already use?** A short comparison table is the first thing under the install buttons.

If any of those four answers is missing or buried below the fold, fix the README before asking for stars.

## Repository Metadata

Suggested description (already in `.github/repository.yml`):

```text
Mac 网络自救工具：Codex、ChatGPT、GitHub 连不上时先定位层级；也能粘贴 HTTP/SOCKS5 代理、预检、部署和回滚。
```

Topics are intentionally scoped to supported search entry points: `macos`, `macos-app`, `network-diagnostics`, `diagnostics`, `proxy`, `socks5`, `dns`, `ipv6`, `tls`, `codex`, `chatgpt`, `github`, `claude`, `cursor`, `kimi`, `mcp`, `model-context-protocol`, `mcp-server`, `clash`, `sing-box`.

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

## Copy-Paste Launch Posts

Use one real case link everywhere:

```text
https://github.com/baishiqi45-dotcom/netfix/blob/main/cases/2026-06-29-%E6%99%AE%E9%80%9A%E7%94%A8%E6%88%B7%E4%BB%A3%E7%90%86%E9%83%A8%E7%BD%B2%E4%BD%93%E9%AA%8C%E5%AE%A1%E6%9F%A5.md
```

Show HN title:

```text
Show HN: Netfix – local-first macOS network triage for AI/dev tool outages
```

Show HN body:

```text
I built Netfix after repeatedly seeing “Codex/GitHub/ChatGPT is unreachable” cases where the real issue was not the AI tool: it was DNS, system proxy, a dead proxy core, IPv6, TLS, or bad pasted proxy credentials.

Netfix is a local-first macOS app/CLI. It diagnoses the broken layer, explains the result in plain language, and only changes system proxy settings after explicit confirmation. If you already have HTTP/SOCKS5 proxy credentials, it can precheck, save to Keychain, apply, monitor, and roll back.

Current state: source-first MIT release. The QA DMG is unsigned/not notarized, so it is for technical testers; run --dry-run first. No telemetry, no proxy selling, no built-in nodes.
```

V2EX / NodeSeek title:

```text
做了个 macOS 本地网络自救工具：Codex / GitHub 连不上时先判断坏在哪一层，也能粘贴代理参数后预检、部署、回滚
```

V2EX / NodeSeek body:

```text
最近一直遇到一种很烦的问题：Mac 上 Codex、ChatGPT、GitHub 或 API 客户端突然连不上，普通用户看不出来是 DNS、系统代理、代理核心、IPv6、TLS、目标服务，还是自己粘贴的代理参数错了。

我做了一个开源小工具 Netfix。它的目标不是卖代理，也不是替代 Clash/Surge，而是在改系统配置前先诊断：哪一层坏了、下一步该点什么、改坏了怎么恢复。

如果你已经有 HTTP/SOCKS5 代理参数，可以在 App 里粘贴 host:port:用户名:密码，先检查能不能连，再保存到 Keychain，最后确认是否让这台 Mac 使用。当前 DMG 还是未签名 QA 版，适合技术测试用户；建议先跑 dry-run 或从源码看。

我最想要的反馈：README 第一屏是否看得懂、安装是否可信、代理参数入口是否清楚、失败提示是否像人话。觉得有用的话也欢迎 star。
```

Reddit short post:

```text
I built Netfix, a local-first macOS network triage app for AI/dev tool connectivity issues.

It tries to answer: is Codex/GitHub/ChatGPT failing because of DNS, system proxy, proxy core, IPv6, TLS, the target service, or pasted proxy credentials?

It can also precheck HTTP/SOCKS5 credentials, save them to Keychain, apply system proxy settings only after confirmation, and roll back.

Current state: MIT source-first release. The QA DMG is unsigned/not notarized, so treat it as technical testing and run --dry-run first. No telemetry, no built-in proxy nodes.
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

## 30-Star Sprint

| Step | Goal | Output |
|---|---|---|
| Day 1 | Make the repo trustworthy | GitHub About/topics set, README says unsigned QA plainly, dry-run comes before install |
| Day 2 | Show one real story | Link the ordinary-user proxy deployment case from README and every launch post |
| Day 3 | Post once in Chinese | V2EX / NodeSeek post with the same case link and no exaggerated claims |
| Day 4 | Collect friction | Turn the first 3 confusing comments into README fixes or issues |
| Day 5 | Post once in English | Reddit or Show HN only after the README first screen is stable |
| After 30 stars | Earn the follow-up | Publish a before/after diagnosis case and the next signed-DMG roadmap |

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
