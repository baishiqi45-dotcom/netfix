# Netfix Productization Plan - 2026-06-24

> Scope: phase-1 product audit and landing plan for turning netfix from a local diagnostic tool into a mature, trusted macOS network rescue product.
> This is a working plan, not proof of product-market fit.

## 1. Current Verdict

Netfix is valuable, but the product story is still too broad.

The current repository already has a strong technical base: CLI diagnostics, JSON reports, HTTP API, MCP server, layered probes, rule-based reasoning, fix tiers, rollback journal, web UI, Swift app direction, and documented safety rules.

The weak point is not "lack of features". It is that the market promise is split between:

- "Codex/OpenAI/GitHub emergency diagnosis"
- "full macOS network self-healing"
- "proxy/VPN troubleshooting"
- "agent-operable network toolkit"

The first version should not try to be all of them equally.

## 2. Recommended Market Wedge

Position netfix as:

**A local macOS network emergency assistant for AI developer tools.**

Concrete promise:

> When Codex, Claude Code, Cursor, GitHub, OpenAI, Kimi Code, or similar AI/dev tools cannot connect, netfix typically tells the user within 30-60 seconds whether the fault is DNS, system proxy, proxy core, proxy node, PAC/WPAD conflict, IPv6 fallback, TLS, Wi-Fi, or remote service reachability, then offers the safest next action.

This wedge is narrow enough to be credible and urgent, but broad enough to grow into a general network self-healing layer later.

## 3. Target Customers

Primary ICP:

- macOS AI developers using Codex, Claude Code, Cursor, GitHub Copilot, OpenAI APIs, Kimi Code, or similar tools.
- They already use proxies, API keys, local CLIs, and terminal workflows.
- They lose real work time when "the model is not thinking", reconnects repeatedly, or hangs before first response.

Secondary ICP:

- Power users who maintain Clash, Surge, v2rayN, sing-box, mihomo, or xray setups for themselves or a small team.
- Support engineers or small-company IT staff who need repeatable local diagnosis reports.

Not the first ICP:

- Consumer VPN buyers.
- Enterprise firewall observability buyers.
- General "make my Wi-Fi faster" users.
- A proxy client replacement market.

## 4. Competitive Context

Market signal exists, but netfix must not copy the wrong category.

- Proxyman sells a macOS network debugging proxy and now advertises AI tool/MCP integration. Its Standard license is listed at $89, which suggests developers will pay for polished local network tooling when the workflow is clear: https://proxyman.com/pricing
- Little Snitch is a mature macOS network monitor/firewall with a $59 single license, showing the macOS network utility category has paid precedent: https://obdev.at/press/2024-05-21.html
- Setapp's Mac subscription pricing gives a reference point for consumer/prosumer Mac software distribution: https://setapp.com/pricing
- Apple VPN-related App Store rules are strict, including NEVPNManager and privacy obligations; a full netfix product should prefer Developer ID notarized distribution unless it deliberately becomes an App Store-compliant network extension product: https://developer.apple.com/app-store/review/guidelines/
- Apple recommends Developer ID signing and notarization for software distributed outside the Mac App Store: https://help.apple.com/xcode/mac/current/en.lproj/dev9b7736b0e.html

Implication: netfix should sell as a local diagnosis and repair assistant, not as a VPN/proxy client.

## 5. Product Power

The strongest product power should be:

1. Deterministic local diagnosis first.
2. Human-readable root cause second.
3. Safe repair third.
4. Agent/MCP operation only after safety contracts are enforced.

Netfix should win because it can answer:

- Is the target service reachable directly?
- Is it reachable through the active proxy?
- Is the local proxy core alive?
- Is macOS system proxy state contradictory?
- Is PAC/WPAD fighting manual proxy settings?
- Is IPv6 fallback creating ambiguous behavior?
- Is the problem local, node-level, DNS-level, TLS-level, or service-level?
- What exact action is safe now?

The product should avoid claiming "one-click fix everything". The mature promise is:

> Netfix never guesses silently. It diagnoses, ranks confidence, separates auto-fix from confirm-fix from manual steps, and verifies after action.

## 6. Architecture Target

Recommended macro architecture:

```text
interfaces/
  cli
  http_api
  mcp_server
  gui_web
  mac_app

application/
  run_diagnostic
  explain_report
  plan_fix
  execute_fix
  rollback
  job_queue

domain/
  report_schema
  diagnostic_contracts
  reasoner
  safety_tiers
  fix_contracts

diagnostics/
  registry
  layers
  service_groups
  proxy_core_adapters

infrastructure/
  command_runner
  privilege_runner
  persistence
  redaction
  packaging

knowledge/
  rules
  cases
  runbooks
```

Key architectural rule:

> All mutating actions must go through one safety gate: plan -> preview -> confirm if needed -> execute -> verify -> journal -> rollback.

CLI, HTTP, MCP, web UI, and Swift app should not each invent their own mutation path.

## 7. Phase-1 Fixes Already Applied

This phase already landed two trust-critical fixes:

- Tier 2 fixes can no longer be approved by `auto_confirm` / `--yes`; they always call the confirmation path.
- MCP mutating tools now advertise both `readOnlyHint: false` and `destructiveHint: true`, so hosts and agents have the correct safety metadata.

Recent diagnostic correctness fixes also improved product clarity:

- HTTP 204 from common connectivity probes is treated as success where appropriate.
- Mixed manual proxy + PAC/WPAD auto proxy is detected as a distinct warning.
- IPv6 default route without observed public IPv6 is reported as fallback risk, not falsely as confirmed IPv6 exposure.
- `codex --json` now includes system proxy state, so the standard entry catches mixed proxy/PAC conflicts.

## 8. P0 Remaining Before Product Push

These are product-blocking, not polish:

1. Route all MCP mutating tools through `FixEngine`, or remove direct mutation tools.
2. Make verification failure affect fix result status, not only `verified`.
3. Strengthen rollback result truthfulness: every restore and reverse command must be counted.
4. Add HTTP `/run` command allowlist and a local auth/CSRF story before exposing web control beyond localhost assumptions.
5. Add privacy redaction and consent boundaries for public IP, DNS, routes, listeners, proxy endpoints, and external service probes.
6. Fix packaging truth: if the app claims no Python setup, the bundle must actually include the runtime or a reliable installer.
7. Turn web UI actions into real fix cards from `report.explanation.actions`, with dry-run preview and post-fix verification output.

## 9. 30/60/90-Day Landing Plan

### First 30 Days: Trustable Core

- Enforce a single mutation path through `FixEngine`.
- Add schemas for reports, diagnostics, root causes, fixes, and action cards.
- Add tests for Tier 1/Tier 2/Tier 3 execution, verification failure, rollback, and MCP mutation.
- Make `netfix codex --json` the gold-path product demo.
- Add 10 real-world cases under `cases/`, focused on AI/dev tool connection failures.

Success bar:

- A developer with a broken Codex/OpenAI/GitHub path can run one command and get a credible root cause plus safe next action.

### Days 31-60: Usable Product Surface

- Make the web UI display root cause, confidence, affected layer, actions, manual steps, and verification.
- Add async jobs/progress for long diagnostics.
- Build a minimal signed/notarized macOS app or honest installer path.
- Add onboarding that explains local-only diagnosis, privacy, and what fixes can change.
- Add case capture flow after confirmed resolution.

Success bar:

- A non-authoring user can diagnose and follow the recommended action without reading JSON.

### Days 61-90: Product Strength and Distribution

- Add agent/LLM explanation as optional, redacted, user-controlled layer.
- Add service presets for Codex, Claude Code, Cursor, GitHub, OpenAI API, Kimi Code.
- Add proxy-client-specific manual runbooks for Clash/mihomo/sing-box/xray/v2rayN/Surge.
- Add update channel, crash/log collection with consent, and release packaging.
- Validate pricing/distribution with a small private beta.

Success bar:

- 20-50 real users can run netfix in real incidents, produce comparable reports, and resolve enough cases to justify a paid/pro product path.

## 10. Immediate Next Step

Continue with P0 safety consolidation:

1. Move `netfix_flush_dns`, `netfix_renew_dhcp`, and `netfix_disable_ipv6` behind `FixEngine` definitions.
2. Add tests proving MCP cannot execute Tier 2 changes through `yes`.
3. Make every fix return one of: `dry-run`, `pending_confirmation`, `ok`, `partial`, `failed`, `cancelled`, or `manual`.
4. Make UI/API display that status directly.

This is the correct next engineering step because it protects the user's machine while making every product surface behave consistently.
