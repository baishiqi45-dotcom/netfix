# Contributing to netfix

Thanks for helping make netfix a reliable Codex-down rescue tool.

## Project values

- **Offline-first**: no pip dependencies, no external LLM required at runtime.
- **Safety-first**: every fix belongs to a tier; dangerous commands need confirmation.
- **Data-driven**: real `cases/` drive rule improvements.

## How to run locally

```bash
make lint
make test
make smoke
```

All Python code must be compatible with Python 3.9+ and use only the standard library.

## Adding a new core adapter

1. Create `netfix/cores/<name>.py` subclassing `ProxyCore` from `netfix/cores/base.py`.
2. Implement `name`, `detect()`, `api_url()`, `get_active_profile()`, `get_profiles()`, and optional `switch_profile()`.
3. Register it in `netfix/detect.py`.
4. Add a test in `tests/` and a shell helper in `bin/` if useful.

## Adding a symptom rule

1. Edit `rules/symptoms.json`.
2. Use existing diagnostics or add a new one in `netfix/diagnose.py`.
3. Link a root cause and a fix; set the correct `tier`.
4. Add a unit test or a `cases/` example.

## Submitting a case

When netfix correctly diagnosed or fixed a real outage, save the report:

```bash
python3 netfix.py codex --save-case
```

Then open a PR with the case under `cases/`. Remove any sensitive IP/domain info if needed.

## Release process (maintainers)

1. Update `netfix/__init__.py` version.
2. Run `make lint test smoke`.
3. Tag `vX.Y.Z` and push.
4. GitHub Actions builds and tests on macOS.
5. (Future) Attach a single-file binary built with PyInstaller.
