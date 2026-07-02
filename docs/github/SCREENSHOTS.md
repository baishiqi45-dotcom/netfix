# Screenshot And Image Plan

The repository includes controlled bilingual SVG assets now. Real app screenshots and GIFs should be added after a clean demo profile is prepared, so no local desktop, proxy password, API key, report path, or real provider account leaks into the public repo.

## Current Assets

| Purpose | Chinese | English |
|---|---|---|
| README hero | `assets/github/hero.zh.png` | `assets/github/hero.en.png` |
| User workflow | `assets/github/workflow.zh.png` | `assets/github/workflow.en.png` |
| Social preview | `assets/github/social-preview.zh.png` | `assets/github/social-preview.en.png` |

Editable SVG sources live next to those PNG files.

## Real Screenshots To Capture

Use sanitized data only:

1. App dashboard after a successful one-click diagnosis.
2. Diagnosis result with a plain-language root cause and a safe next step.
3. Proxy setup with `proxy.example.com:1080:user:<password>`.
4. Proxy precheck result with password masked.
5. Settings -> AI with a fake provider key masked.
6. Settings -> AI Coding Assistant copy flow for Codex and Kimi.
7. Restore original network settings prompt.

## Capture Rules

- Do not capture the real macOS desktop.
- Do not show real proxy hosts, account names, API keys, QR codes, or raw reports.
- Prefer the app window on a plain background.
- Save Chinese screenshots under `assets/github/zh/`.
- Save English screenshots under `assets/github/en/`.
- If a GIF is added, keep it under 8 seconds and show one task only: diagnose, explain, fix or restore.

## Pre-Publish Checks

Run:

```bash
python3 scripts/marketing_claims_check.py --json
python3 scripts/release_audit.py --scope workspace --root .
```

Then inspect every image at full size before linking it from README.
