# Netfix Developer Interfaces

This document owns command-line, local HTTP, MCP, source-run, and P0 release-build details. The root READMEs remain focused on the user flow: paste an existing HTTP/SOCKS proxy, verify it, explicitly enable it, then stop and restore it when finished.

## CLI

Run commands from the repository root:

```bash
python3 netfix.py codex --json
python3 netfix.py triage --json
python3 netfix.py doctor --json
python3 netfix.py kb --query MTU
```

Compatibility aliases are `check` for `triage`, `full-check` for `doctor`, and `guide` for `kb`. `fix` and `rollback` are mutating surfaces; Tier 2 actions require explicit user confirmation as defined in [AGENTS.md](../../AGENTS.md). Generic Tier 2 fixes without `transactional_rollback=true` are preview-only and return `transactional_rollback_unavailable` instead of leaving partially changed system state.

For a source checkout:

```bash
pip install -e .
python3 netfix.py server --host 127.0.0.1 --port 0
```

## HTTP API

The server binds to `127.0.0.1`. Non-public reads and every POST require the local `X-Netfix-Token`; the token path is printed by the server and is also available to the app-owned runtime.

Core endpoints:

- `GET /health`
- `GET /capabilities`
- `POST /run` with `{ "command": ["codex"], "timeout": 30, "async": false }`
- `GET /jobs/<id>`
- `GET /report/latest`
- `GET /services/groups`
- `GET /dashboard/state`
- `GET /llm/providers`
- `POST /settings/llm`
- `POST /explain_llm`

Example:

```bash
curl -s http://127.0.0.1:8765/run \
  -H "X-Netfix-Token: $NETFIX_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":["codex"],"timeout":30,"async":false}'
```

Treat the command and endpoint lists above as the current interface contract.

### Optional AI explanation API

AI explanation is outside the P0 proxy flow. Network checks, proxy validation,
enablement, and recovery do not require an AI key. To configure the optional
explanation service through HTTP, use the settings endpoint rather than the
read-only provider list:

```bash
curl -s http://127.0.0.1:8765/settings/llm \
  -H "X-Netfix-Token: $NETFIX_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"provider":"deepseek","api_key":"'"$DEEPSEEK_API_KEY"'","fallback":{"enabled":true,"chain":["deepseek","moonshot_kimi","minimax","qwen"],"vision_chain":["minimax","moonshot_kimi","qwen"]},"budget":{"persist_usage_ledger":true}}'
```

Provider-scoped process configuration may use
`NETFIX_LLM_API_KEY_DEEPSEEK`; keys are never shared implicitly across
fallback providers.

Cloud explanation requires explicit upload consent. Image questions also
require the feature to be enabled and per-request confirmation:

```bash
curl -s http://127.0.0.1:8765/explain_llm \
  -H "X-Netfix-Token: $NETFIX_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"image_question","upload_confirmed":true,"images":["data:image/png;base64,..."]}'
```

DeepSeek is the default text-explanation route. Image questions use a
configured MiniMax, Kimi/Moonshot, or Qwen vision adapter. Netfix does not
claim that DeepSeek is an image model, and no MCP tool can save an AI key or a
proxy password.

## MCP

Start the stdio server with:

```bash
python3 -m netfix.mcp_server
```

Primary tools include `netfix_codex`, `netfix_services`, `netfix_triage`, `netfix_doctor`, `netfix_report`, `netfix_kb_query`, `netfix_list_fixes`, `netfix_dry_run_fix`, `netfix_apply_fix`, `netfix_evidence_chain`, and `netfix_sanitized_report`. Compatibility tools such as `netfix_fix_issue`, `netfix_rollback`, and `netfix_proxy_switch` remain available while their contracts are tested. `netfix_rollback` requires `confirmed=true` with `confirmation=APPLY_SYSTEM_FIX`; `/run` rejects `rollback` because that endpoint has no action-time confirmation channel.

Registration helpers:

```bash
./scripts/install_mcp.sh --codex
./scripts/install_mcp.sh --kimi
./scripts/install_mcp.sh --all --dry-run
```

An installed App also exposes a copy path at **Settings -> Advanced &
Developer -> AI Coding Assistant**. Use **Copy for Codex** or **Copy Kimi /
generic config**; the generated stdio configuration points at the MCP server
inside the installed App, so an App user does not need the source checkout.

The optional AI MCP surfaces are `netfix_llm_providers` and
`netfix_explain_llm`. Image mode uses the same safety gate as HTTP:

```yaml
name: netfix_explain_llm
arguments:
  mode: "image_question"
  upload_confirmed: true
  images:
    - "data:image/png;base64,..."
```

Mutating MCP calls do not grant themselves permission. Follow the confirmation phrases and Tier rules in [AGENTS.md](../../AGENTS.md).

## P0 macOS Candidate

Build from the repository root or `gui/macos` without installing new tools:

```bash
gui/macos/build_app.sh --release-candidate
```

The build searches only existing local PyInstaller environments, compiles a fresh standalone `netfix-backend`, copies it to `Netfix.app/Contents/MacOS/netfix-backend`, and fails if that executable is missing. The Swift runtime already resolves that bundle executable before bundled or system Python fallbacks, so a valid candidate does not require system Python at runtime.

`pyproject.toml` is the only version authority. The generated `Contents/Resources/release-manifest.json` uses schema `netfix_release_manifest.v1` and records:

- `git_sha`
- `dirty`
- `source_fingerprint`
- `backend_sha256`
- `app_executable_sha256`
- `build_id`
- `built_at`
- `version`

Creation and verification are explicit:

```bash
python3 scripts/release_manifest.py version --repo-root .
python3 scripts/release_manifest.py verify \
  --app-bundle gui/macos/.build/Netfix.app \
  --manifest gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json \
  --repo-root .
scripts/verify_dmg_backend.sh
```

Both missing executables and SHA-256 mismatches fail closed. The build does not quit, launch, or install the app, and does not create or modify desktop links.

The current P0 artifact is an unsigned, unnotarized candidate: it is not Developer ID signed and is not notarized. Ad-hoc signing of the nested backend only makes the local executable runnable; it is not an Apple distribution signature.
