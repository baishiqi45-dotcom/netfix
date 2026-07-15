# Netfix Capability Matrix

This file is the owner-repo authority map for Netfix product surfaces. AIKB notes
and research reports can cite it, but they do not replace it.

## Surface Authority

| Layer | Primary owner | Read-only entry | Mutating entry | Confirmation rule | Contract / tests |
|---|---|---|---|---|---|
| App | macOS UI | Dashboard state, reports, logs | Proxy apply, rollback, key save | Any system proxy change must show App confirmation | `DashboardStateResponse`, Swift tests |
| CLI | `netfix.py` | `codex`, `triage`, `doctor`, `kb`, `report`, `logs` | `fix`, `rollback`, `proxy-switch` | Tier 2 ignores `--yes`; confirmation plus verified transactional rollback required | CLI parser/docs tests |
| HTTP | local server | `GET /health`, `/dashboard/state`, `/report/latest`, `/llm/providers` | `POST /run`, `/fixes/execute`, `/settings/llm`, `/proxy/*` | Non-public GET and all POST require token; system fixes require magic phrase | API tests |
| MCP | `netfix.mcp_server` | report, services, evidence, sanitized report | fix/apply/rollback/proxy switch tools | Mutating tools must expose destructive annotations and confirmation schema | MCP tests |
| Web | local dashboard | current Mac state, report, logs | Calls authenticated HTTP endpoints only | Web must not bypass HTTP confirmation | Web UI tests |

## Capability Classes

| Class | Examples | Product rule |
|---|---|---|
| Core | paste an existing HTTP/SOCKS proxy, verify, save, explicitly enable, stop, restore | Must be visible from App without reading docs |
| Advanced | egress/IP reputation, AI explanation, batch import/export, monitor | Hidden behind task or advanced surfaces |
| Developer | structured diagnosis, CLI, HTTP API, MCP, release verification | Document under `docs/developer/`, not as the root README promise |
| Internal | jobs, tokens, backend lifecycle, schema plumbing | Not marketed as user features |
| Compat | old MCP tools, CLI aliases `check/full-check/guide` | Keep tested or remove from docs |

## P0 Release Candidate Contract

The macOS candidate must contain the executable
`Netfix.app/Contents/MacOS/netfix-backend`. The app runtime resolves this
bundle executable first, and a valid candidate does not require system Python.
`gui/macos/build_app.sh` builds the backend from repository source with an
already-available local PyInstaller; it does not install build tools.

`pyproject.toml` is the version authority. The embedded
`release-manifest.json` records `git_sha`, `dirty`, `source_fingerprint`,
`backend_sha256`, `app_executable_sha256`, `build_id`, `built_at`, and
`version`. Missing backend or app executables and either SHA-256 mismatch are
hard failures in manifest verification and DMG verification.

The current artifact is an unsigned, unnotarized candidate. It is not
Developer ID signed and is not notarized. The build must not quit or launch
the app, install it, or modify desktop links.

## Current Network Identity

`GET /dashboard/state` returns `schema_version: "netfix_current_mac_state.v2"`.
It is the authority for first-screen state in both macOS and Web. The top
level now also mirrors `verdict.headline / verdict.detail / verdict.next_step`
as `headline / detail / next_step` so legacy clients can read the home
narrative without descending into the `verdict` block.

Mandatory invariants enforced by `tests/test_dashboard_state_contract.py`:

- External system proxy + fresh ok report → `verdict.severity` MUST be
  `info` (never `ok`), and `proxy.verified.status` MUST stay `unknown` when
  no journal report exists. Netfix has not verified end-to-end.
- `unknown / unchecked / notSampled` diagnostic counts MUST NOT contribute
  to `issue_count`.
- `effective_route == "external_system_proxy"` is the only route that
  downgrades a green ok to info when a journal report arrives.

- `decision`: single UI state and primary action.
- `machine`: interface, local IP, gateway, IPv6 route.
- `proxy`: saved profiles, system proxy, bridge, applied owner, verification.
- `egress`: latest cached/report-based exit identity, or `unchecked`.
- `state`: legacy six-state block for older UI compatibility.

The dashboard must not trigger a live external IP lookup just by opening. Live
egress checks belong to diagnosis, apply verification, or explicit user action.

## Confirmation Boundary

LLM output, docs, dashboard copy, and MCP read-only tools cannot grant execution
permission. Any action that changes system proxy, DNS, IPv6, rollback state,
Keychain secrets, or provider settings must flow through the App/HTTP/MCP
confirmation contract and fail closed when confirmation is missing.
