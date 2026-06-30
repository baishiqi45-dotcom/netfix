# Netfix End User License Agreement Draft

Last updated: 2026-06-24

This draft is for productization and legal review. It should not be published as final legal text until reviewed.

## License

Netfix grants the user a limited, non-transferable license to install and use the application on macOS devices owned or controlled by the user, subject to the final purchase terms.

## Intended Use

Netfix is intended for local network diagnostics, safe repair planning, and monitoring of user-authorized network and proxy configurations.

Netfix does not provide, sell, resell, broker, or recommend residential IP addresses, VPN services, proxy nodes, account automation services, or methods to bypass third-party platform controls.

## User Responsibilities

The user is responsible for:

- Using Netfix only on devices and networks they own or are authorized to administer.
- Ensuring any proxy, VPN, or residential IP service used with Netfix was legally obtained and complies with the provider's terms.
- Reviewing dry-run plans and confirmation prompts before applying configuration changes.
- Keeping API keys, proxy credentials, and account credentials secure.

## Prohibited Use

The user may not use Netfix to:

- Bypass bans, fraud controls, rate limits, paywalls, access controls, or geographic restrictions in violation of law or third-party terms.
- Conduct credential stuffing, scraping without authorization, spam, bot activity, bulk registration, account farming, or similar abuse.
- Access networks, systems, services, or data without authorization.
- Resell Netfix as a proxy or VPN service.
- Reverse engineer or modify Netfix except where allowed by applicable law or the open-source license for source components.

## Safety Tiers

Netfix classifies repair actions by safety level. Tier 2 or higher configuration changes require explicit user confirmation. Netfix may provide manual steps for actions that should not be automated.

## No Guarantee

Netfix does not guarantee that any website, API, proxy endpoint, residential IP, or developer tool will remain reachable, accepted, low-risk, or compliant with a third-party platform's policies.

Network conditions, provider policies, proxy quality, authentication status, DNS behavior, and platform rules can change outside Netfix's control.

## Local And Cloud Components

Netfix runs diagnostics locally. Optional cloud AI explanation may use the LLM provider configured by the user. Cloud explanations are advisory and do not override local safety checks.

When image question is enabled, Netfix may strip supported image file metadata before upload, but it does not guarantee automatic removal of visible secrets contained in screenshots or photos. Users are responsible for cropping or masking sensitive visual content before sending images to a cloud AI provider.

## Limitation Of Liability

To the maximum extent permitted by law, Netfix is provided without warranties of uninterrupted availability, error-free operation, or fitness for prohibited or unauthorized purposes.

## Legal Review Notes

Before public distribution, this EULA needs legal review for:

- Paid-license terms and refund policy.
- Warranty disclaimers and liability limits by jurisdiction.
- Open-source dependency/license compatibility.
- Apple Developer ID distribution requirements.
