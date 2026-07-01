## Summary

-

## Verification

- [ ] `python3 -m pytest -q`
- [ ] `cd gui/macos && swift build`
- [ ] For release/package changes: `./scripts/release_gate.sh --strict-workspace`

## Safety

- [ ] I did not include real proxy URLs, API keys, cookies, QR codes, or raw reports.
- [ ] User-facing errors use plain language instead of internal reason codes.
- [ ] Any Tier 2 system change still requires explicit confirmation.
