## Summary

-

## Architecture

- [ ] Apple Silicon (arm64)
- [ ] Intel (x86_64)
- [ ] macOS 14
- [ ] macOS 15
- [ ] macOS 26
- [ ] N/A (no runtime impact)

## Affected Areas

- [ ] `rules/` (symptoms / services JSON)
- [ ] `netfix/cores/` (proxy-core adapter)
- [ ] `netfix/mcp_server.py` (MCP tool surface)
- [ ] `netfix/llm_explain.py` or providers
- [ ] `netfix/proxy_bridge.py` / `residential_proxy.py`
- [ ] `gui/macos/` (SwiftUI)
- [ ] CI / release scripts
- [ ] Docs / README / Issue templates
- [ ] N/A

## Output Schema Impact

- [ ] `python3 netfix.py codex --json` output shape changed
- [ ] `rules/symptoms.json` schema changed
- [ ] MCP `tools/list` changed (added / removed / renamed)
- [ ] I updated the schema references in `docs/` and `.github/ISSUE_TEMPLATE/safe_diagnostic_report.md`
- [ ] N/A

## Verification

- [ ] `python3 -m pytest -q`
- [ ] `cd gui/macos && swift build`
- [ ] For release/package changes: `./scripts/release_gate.sh --strict-workspace`
- [ ] For MCP changes: smoke-tested `netfix_codex`, `netfix_fix_issue`, `netfix_rollback`
- [ ] For rules changes: added or updated a sanitized `cases/` example

## Safety

- [ ] I did not include real proxy URLs, API keys, cookies, QR codes, or raw reports.
- [ ] User-facing errors use plain language instead of internal reason codes.
- [ ] Any Tier 2 system change still requires explicit confirmation.
- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md) and [SECURITY.md](../SECURITY.md).
- [ ] N/A (docs / formatting only)

## Linked Issues

- Fixes # / Relates to # / N/A