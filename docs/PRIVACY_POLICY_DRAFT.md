# Netfix Privacy Policy Draft

Last updated: 2026-06-24

This draft is for productization and legal review. It should not be published as final legal text until reviewed.

## Product Scope

Netfix is a local-first macOS network diagnostic and repair assistant for AI and developer tools. Netfix does not sell, bundle, recommend, or resell residential IP services, VPN services, or proxy nodes.

## Data Netfix Reads Locally

Netfix may read the following local state to diagnose connectivity problems:

- macOS network interface, gateway, DNS, route, and system proxy settings.
- Local listening ports and running proxy core process names.
- Local proxy client metadata such as profile names, active profile, endpoint host, port, and protocol.
- Diagnostic probe results for selected services such as OpenAI, GitHub, npm, PyPI, and user-selected endpoints.
- User-provided proxy profile fields when the user pastes credentials into the proxy setup flow.

## Data Stored Locally

Netfix stores local settings and logs under `~/.netfix`:

- `settings.json`: non-secret preferences, provider IDs, model IDs, and non-secret proxy profile metadata.
- `last_report.json`: the latest diagnostic report, if "save latest report" is enabled.
- `events.jsonl`: lightweight event history for the local timeline.
- Fix journal/audit files used to support rollback and troubleshooting.
- Local cloud-AI budget ledger entries containing provider id, mode, timestamp, and cooldown expiry only; prompts, images, provider responses, API keys, and proxy credentials are not stored in this ledger.

LLM API keys and proxy passwords are stored in macOS Keychain, not in `settings.json`.

Users can change event-log retention and clear local report/event logs from Netfix settings or the CLI. Users can also disable persistent local cloud-AI budget counting; disabling persistence, disabling the local AI budget, or deleting all Netfix local data removes the local AI budget ledger.

## Cloud AI Explanation

Cloud AI explanation is optional. When enabled, Netfix sends a redacted report to the provider selected by the user, such as DeepSeek, Kimi/Moonshot, MiniMax, Qwen, a custom OpenAI-compatible endpoint, or OpenAI.

Before sending a report to an LLM provider, Netfix removes or replaces sensitive fields such as:

- API keys, passwords, tokens, UUIDs, and subscription URLs.
- Raw stdout/stderr and command output.
- Hostname and full public IP address.
- Proxy profile hosts and credentials.
- Sensitive query parameters.

If image question is enabled and the user confirms an image upload, Netfix strips supported image file metadata before calling the provider. Netfix does not automatically read, blur, or redact visible text or pixels inside an image; users should crop or mask proxy passwords, API keys, account identifiers, and other secrets before upload.

LLM output is advisory only. Netfix does not execute shell commands invented by an LLM. Executable actions must match locally known fix IDs and remain governed by local safety tiers.

## Network Probes

Netfix performs network probes to determine whether services are reachable. These probes may contact third-party services such as GitHub, OpenAI, Anthropic, npm, PyPI, Docker Hub, and public connectivity endpoints. The contacted service may receive standard connection metadata such as IP address, user agent, and timestamp.

## Residential Or Custom Proxy Profiles

Netfix helps users validate and monitor proxy credentials they legally obtained elsewhere. Netfix does not verify the legal origin of a proxy service and does not guarantee that an endpoint is residential, low-risk, or accepted by any third-party platform.

Netfix should not be used to bypass bans, evade fraud controls, automate abuse, or access systems without authorization.

## User Controls

Users can:

- Disable cloud AI explanation.
- Choose the LLM provider and model.
- Clear local report/event logs.
- Disable saving the latest full report.
- Change event-log retention days.
- Delete saved Keychain items using macOS Keychain Access.

## Data Sharing

Netfix does not sell user data. Netfix does not upload diagnostic reports unless the user enables cloud AI explanation or explicitly exports/shares a report.

## Legal Review Notes

Before public distribution, this policy needs review for:

- Apple App Privacy labels.
- Region-specific privacy law requirements.
- LLM provider data processing terms.
- Crash reporting or telemetry, if added later.
