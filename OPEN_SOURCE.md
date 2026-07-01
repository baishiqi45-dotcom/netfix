# Netfix Open-Source Release Guide

Netfix is intended to be published as a source-first open-source project before it is distributed as a signed macOS binary. The source release must be easy to read, safe to audit, and free of local credentials, local reports, generated binaries, or private planning notes.

## Public Positioning

- Name: `netfix` or `netfix-macos`.
- One-line description: local-first macOS network triage for AI and developer tools.
- License: MIT.
- Primary user: macOS users who rely on Codex, ChatGPT, GitHub, API clients, and proxy-based developer workflows.
- Primary promise: diagnose the broken layer first, explain it plainly, and apply reversible fixes only after confirmation.

Do not position Netfix as a proxy seller, access provider, account workaround, or guaranteed route-quality product.

## Publishable Units

There are two different release states:

| Unit | Status meaning | How to publish |
|---|---|---|
| Clean source export | Public source snapshot passed audit | Publish `open-source-export/Netfix-0.2.0-source` or its zip |
| Current development workspace | Local working tree may contain QA artifacts | Publish only if workspace audit is clean |
| Download QA package | Unsigned candidate package passed smoke checks | Share only as QA artifact |
| Paid external macOS release | Signed, notarized, legally reviewed, clean-machine tested | Publish only after all paid-release blockers are clear |

The safe default is the clean source export. It is generated from the current tree but excludes local proxy packages, generated DMG/ZIP artifacts, build outputs, runtime state, private cases, and internal docs.

## Required Checks

Run these before source publication:

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke
python3 scripts/release_preflight.py --with-dmg-smoke --json
python3 scripts/release_preflight.py --with-dmg-smoke \
  --write-record gui/macos/.build/release-export/Netfix-0.2.0-macos/download-qa-preflight.json
(cd gui/macos/.build/release-export/Netfix-0.2.0-macos && python3 verify-download.py --require-recorded-preflight)
```

If `release_audit` reports `tracked-release-artifact`, remove generated release files from the git index without deleting local QA files:

```bash
git ls-files 'Netfix-*.dmg' 'Netfix-*.zip'
git rm --cached Netfix-0.2.0.dmg Netfix-0.2.0-macos.zip
python3 scripts/release_audit.py --scope workspace --root .
```

CI must treat `python3 scripts/release_audit.py --scope workspace --root .` as a hard gate.

## GitHub Checklist

- Add `README.md` and `README.en.md` with matching Chinese/English first screens.
- Add visual assets under `assets/github/` in both `.zh` and `.en` variants.
- Add `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue templates, and PR template.
- Set repository topics from `.github/repository.yml`.
- Use `docs/github/STAR_GUIDE.md` for the public launch checklist.
- Use `docs/github/SCREENSHOTS.md` to track real App screenshots and GIFs before a binary release.

## Binary Release Boundary

Unsigned local App candidates are useful for development and QA, but they are not the public product. A public macOS binary release must have:

- Developer ID signing.
- Apple notarization.
- Clean-machine install and launch evidence.
- Local backend smoke evidence from the packaged app.
- Legal review of privacy policy and EULA drafts.
- Live provider smoke evidence for optional cloud AI paths.

Until those are complete, public docs should say “build from source” or “source release”, not “download the finished app”.

## Community Contributions

Good contributions are small, reproducible, and sanitized:

- new symptom rules in `rules/symptoms.json`
- new service definitions in `rules/services.json`
- new proxy-core adapters in `netfix/cores/`
- sanitized cases in `cases/`
- clearer app copy, docs, and screenshots

GitHub Issues and PRs must not include real proxy passwords, API keys, QR codes, cookies, bearer tokens, screenshots with visible secrets, or raw diagnostic reports.
