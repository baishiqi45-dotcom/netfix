# Netfix

[中文 README](README.md)

![Netfix - paste, verify, and safely enable an existing proxy](assets/github/hero.en.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macOS-blue)
![privacy: local first](https://img.shields.io/badge/privacy-local--first-0f766e)

> **Netfix handles HTTP/HTTPS/SOCKS proxy credentials you already have: paste the connection details, verify them first, then enable the proxy safely after explicit confirmation; you can stop it and restore the previously saved network settings at any time.**

## Get Started

The current macOS candidate is **not Developer ID signed and not notarized**. It is for technical testing only and must not be presented as a finished installer for general users. If macOS blocks it, use **Open Anyway** in System Settings -> Privacy & Security.

The system requirement is macOS 13 or newer.

1. Drag `Netfix.app` from the candidate DMG into Applications. If macOS blocks the first launch, confirm it in System Settings -> Privacy & Security.
2. Copy HTTP, HTTPS, or SOCKS5 connection parameters from a proxy service you legally own or operate, then paste them into Netfix.
3. Verify the connection first. Netfix only enables the proxy after verification succeeds and you explicitly confirm the change.
4. When finished, stop the proxy in the app and restore the network settings saved before enablement.

Common input formats:

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

Copy connection parameters from the provider dashboard, not the current exit IP shown by an IP lookup page. Netfix does not currently parse `ss://`, `vmess://`, or Clash/sing-box subscription links.

Authenticated HTTP/HTTPS/SOCKS connections are forwarded locally by Netfix, while passwords remain in macOS Keychain.

![Netfix user path](assets/github/workflow.en.png)

## Stop And Restore

Netfix saves the current system network settings before enabling a proxy. To stop, use the app to disable the proxy and restore that saved state. Treat the state shown in the app as the result; restarting the Mac is not a recovery guarantee.

## Safety Boundary

- **No proxy selling.** Netfix does not ship built-in nodes or promise provider or exit quality.
- Proxy passwords belong in macOS Keychain and must not appear in logs, reports, screenshots, release packages, or GitHub Issues.
- Every system proxy change requires user confirmation; a failed verification never enables the proxy automatically.
- Netfix does not help bypass third-party account, risk-control, geographic, or abuse policies.

## Project Material

Technical testers who used the candidate installer can remove the local app with its `--uninstall` option; the installer source is [`scripts/install_mac_app_from_github.sh`](scripts/install_mac_app_from_github.sh).

Sanitized usage records are indexed in [Case Index](cases/INDEX.md). Engineering integration, source execution, build, and release verification are in the [developer documentation](docs/developer/interfaces.md). Read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before contributing.

## License

MIT
