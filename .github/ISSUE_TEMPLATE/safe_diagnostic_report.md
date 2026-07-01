---
name: Sanitized diagnostic report
about: Share a Netfix diagnosis safely
title: "[Diagnostic] "
labels: diagnostic
---

## Symptom


## Sanitized Netfix Output

Paste only the relevant redacted fields from `python3 netfix.py codex --json`.

```json
{
  "environment": {
    "active_profile": "<redacted>",
    "active_core": "<redacted>"
  },
  "diagnostics": [],
  "root_causes": [],
  "fixes": [],
  "manual_steps": []
}
```

## What you tried

- [ ] One-click diagnosis
- [ ] Proxy precheck
- [ ] Restore original network settings
- [ ] MCP / Agent call

## Redaction Checklist

- [ ] No real proxy passwords
- [ ] No API keys
- [ ] No cookies or bearer tokens
- [ ] No QR codes
- [ ] No raw reports
- [ ] No screenshots with visible secrets
