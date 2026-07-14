# Netfix

[English README](README.en.md)

![Netfix - 粘贴、验证并安全启用已有代理](assets/github/hero.zh.png)

![license: MIT](https://img.shields.io/badge/license-MIT-green)
![platform: macOS](https://img.shields.io/badge/platform-macos-blue)
![privacy: 本地优先](https://img.shields.io/badge/privacy-%E6%9C%AC%E5%9C%B0%E4%BC%98%E5%85%88-0f766e)

> **Netfix 只处理你已有的代理参数，包括 HTTP/HTTPS/SOCKS：粘贴连接信息，先验证可用性，再由你确认后安全启用；任何时候都可以停止代理并恢复启用前的网络设置。**

## 开始使用

当前提供的是 **未签名、未公证的 macOS 候选构建**。它没有使用 Apple Developer ID 签名，也没有通过 Apple 公证，只适合技术测试，不应作为面向普通用户的正式安装包。

系统要求为 macOS 13 或更新版本。

1. 从候选 DMG 中把 `Netfix.app` 拖到「应用程序」。macOS 首次拦截时，到「系统设置 -> 隐私与安全性」点击「仍要打开」。
2. 从你合法拥有或运营的代理服务后台复制 HTTP、HTTPS 或 SOCKS5 连接参数，粘贴到 Netfix。
3. 先运行可用性验证。只有验证通过并得到你的明确确认后，才能点击「开始使用代理」。
4. 不再使用时，在 App 中停止代理并恢复启用前保存的网络设置。

常见输入格式：

```text
socks5h://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8000
proxy.example.com:1080:user:pass
host,port,username,password
```

请复制服务商提供的连接参数，不要复制 IP 查询网页显示的「当前出口 IP」。Netfix 暂不解析 `ss://`、`vmess://` 或 Clash/sing-box 订阅链接。

有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发，密码仍保存在 macOS Keychain。

![Netfix 用户路径](assets/github/workflow.zh.png)

## 停止与恢复

Netfix 在启用代理前保存当时的系统网络设置。需要停用时，在 App 中停止代理并恢复这份已保存设置。恢复是否完成应以 App 的当前状态为准，不把重启电脑当作恢复保证。

## 安全边界

- **不卖代理。** Netfix 不内置节点，也不承诺第三方服务质量或出口质量。
- 代理密码保存在 macOS Keychain，不应进入日志、报告、截图、发布包或 GitHub Issue。
- 任何系统代理变更都必须经过用户确认；验证失败不会自动启用代理。
- Netfix 不帮助绕过第三方平台的账号、风控、地域或滥用规则。

## 项目资料

通过候选安装器安装的测试用户，可用安装器的 `--uninstall` 选项移除本机 App；安装器源码见 [`scripts/install_mac_app_from_github.sh`](scripts/install_mac_app_from_github.sh)。

脱敏后的实际使用记录见 [Case Index](cases/INDEX.md)。工程接入、源码运行、构建和发布校验见 [开发者文档](docs/developer/interfaces.md)。贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

## License

MIT
