# Security Policy

Netfix is a local-first network diagnostic and proxy configuration helper.
It may process proxy credentials, API keys, local network settings, and
diagnostic reports on the user's machine.

## Supported Versions

Security fixes target the latest `main` branch and the latest tagged release.

## Reporting A Vulnerability

Use GitHub Private Vulnerability Reporting for this repository when it is
enabled. If it is not enabled yet, open a public issue titled
`Security contact request` and include only a short, sanitized summary. Do not
include exploit details, secrets, live proxy URLs, screenshots with visible
tokens, or raw diagnostic reports in a public issue.

Expected response target: acknowledge within 7 days, then provide either a
fix plan, a request for sanitized reproduction details, or an out-of-scope
decision.

Include:

- affected version or commit
- operating system version
- reproduction steps using sanitized examples
- expected and actual behavior
- whether credentials, local reports, or network settings may be exposed

## Sensitive Data Rules

Do not paste real proxy passwords, API keys, bearer tokens, cookies, or full
supplier proxy URLs into GitHub Issues, pull requests, screenshots, or support
messages. Replace them with examples such as:

```text
proxy.example.com:8000:user:<password>
socks5h://user:<password>@proxy.example.com:1080
sk-...redacted...
```

If you accidentally publish a live credential, rotate it with the provider
first, then remove the public copy.

## Scope

In scope:

- local API token leakage
- Keychain storage mistakes
- proxy credential echo in API/UI/MCP responses
- unsafe system proxy apply or rollback behavior
- release packages that include sensitive local artifacts

Out of scope:

- quality, reputation, or availability of third-party proxy providers
- bypassing third-party abuse, anti-fraud, geo, or account controls
- attacks requiring a malicious local administrator
