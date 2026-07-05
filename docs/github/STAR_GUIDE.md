# GitHub Launch Guide

Stars follow usefulness, not promotion. This file keeps the repository honest, and gives the project a concrete playbook for the moment strangers land on the README.

## First Screen Promise

README 首屏必须在 5 秒内回答四个问题：

1. **这是什么？** 帮普通 Mac 用户把买来的代理参数粘贴进去、检查可用、让 Mac 使用它的本地小工具。
2. **能帮我做什么？** 代理连不上时，告诉我是不是地址抄错、节点挂了、账号失效、DNS 问题，还是系统代理没切过去。
3. **怎么安全试用？** 先看到 `--dry-run`，再看到未签名 QA 版的安装命令；恢复网络的方法一眼可见。
4. **跟 Clash/Surge 有什么不同？** 它们负责转发流量，Netfix 负责告诉你“这台 Mac 现在能不能让代理连上”，并在改之前预检、改之后可恢复。

如果四个答案有任何一个被埋到首屏以下，先改 README，再要 star。

## Repository Metadata

Suggested description (already in `.github/repository.yml`):

```text
买了代理不会配 Mac？把 HTTP/SOCKS5 参数粘贴进 Netfix，先检查、再保存、一键开始使用；随时可恢复原来的网络设置。
```

Topics are intentionally scoped to supported search entry points: `macos`, `macos-app`, `network-diagnostics`, `diagnostics`, `proxy`, `socks5`, `dns`, `ipv6`, `tls`, `codex`, `chatgpt`, `github`, `claude`, `cursor`, `kimi`, `mcp`, `model-context-protocol`, `mcp-server`, `clash`, `sing-box`.

## Comparison Snippet (paste into README)

| 工具 | 它做什么 | Netfix 多做的事 |
|---|---|---|
| **ClashX / Surge / Shadowrocket / sing-box** | 客户端代理 App：你提供节点，它们转发流量。 | Netfix 告诉你**这台 Mac 现在的网络到底能不能让代理连上**，应用前预检，失败可恢复。 |
| **Activity Monitor / `netstat`** | 通用进程/端口检查。 | 一份报告同时覆盖 DNS / 系统代理 / 代理软件 / IPv6 / TLS / 目标服务，告诉你“坏在哪一层”。 |
| **聊天机器人手写 `curl` / `ping`** | 模型临时拼命令。 | 结构化 JSON 输出、分级修复、自动备份原网络、发云端前先脱敏。 |
| **iStat Menus / 网络监控小部件** | 看实时速率/信号。 | 修复向：粘贴参数 → 预检 → 部署 → 监控 → 恢复，一条龙。 |

## Social Proof — 发布前要补的视觉资产

所有截图必须基于**脱敏的演示配置**：没有真实桌面内容、没有真实代理地址、密码用圆点或占位符遮挡。

### 截图/漫画/长图具体脚本

**1. 首屏状态卡片（1 张 PNG）**
- 画面：Netfix 主窗口，顶部状态条显示「代理已保存到这台 Mac，但还没开始使用」。
- 主体：蓝色状态卡片「粘贴代理参数」放在最显眼位置；下方是「一键诊断」按钮。
- 不要出现：终端窗口、日志面板、AI 设置入口抢镜。
- 用途：README 首屏 hero 下方第二张图。

**2. 代理粘贴流程（3 张 PNG 或 1 张纵向长图）**
- 第 1 帧：设置页「让这台 Mac 用代理上网」，输入框 placeholder 显示 `proxy.example.com:8001:username:password`。
- 第 2 帧：点「检查并保存」后显示「已识别：xxx」和绿色可用提示。
- 第 3 帧：点「开始使用代理」后弹出确认框，文案突出「会先备份网络设置，可随时恢复」。
- 用途：README 三步流程配图、小红书/即刻长图。

**3. 失败提示人话化（1 张 PNG）**
- 画面：主界面橙色错误卡片，标题「代理账号或密码不对」，下一步「回服务商后台重新复制完整的地址、端口、用户名和密码」。
- 对比：旁边小字标注「不再显示 reason_code / HTTP 407」。
- 用途：说明「说人话」的产品差异。

**4. 恢复网络设置（1 张 PNG 或 3 秒 GIF）**
- 画面：设置页代理区域，按钮「恢复原来的网络设置」高亮。
- 点击后弹出确认：「这会恢复上次部署代理前备份的 macOS 网络代理设置。」
- 用途：消除用户「会不会改坏网络」的顾虑。

**5. 终端 JSON 诊断（1 张 8 秒 GIF）**
- 画面：Terminal 运行 `python3 netfix.py codex --json`。
- 内容：显示 `root_causes` 和 `fixes`，但关键字段已脱敏。
- 用途：技术社区证明「真的有本地诊断引擎」。

**6. 真实 case 链接**
- 至少从 `cases/2026-06-29-普通用户代理部署体验审查.md` 引一段到 README「真实 case 速览」。

### 文件存放

- 中文截图：`assets/github/zh/`
- 英文截图：`assets/github/en/`
- 动图：同名 `.gif`，不超过 5MB。

## Cases Worth Linking From The README

These exist already and are ready to be quoted (each must be sanitized before linking):

- `cases/20260617-1405-codex-reachable-needs-key.md` — "Codex 网络通但 API Key 失效" 的经典场景。
- `cases/2026-06-17-healthy-baseline.md` — 健康基线作为 before/after 对照。
- `cases/2026-06-29-普通用户代理部署体验审查.md` — 普通用户视角的痛点，最适合做 "Real user story" 引流。
- `cases/TEMPLATE.md` — 模板，提醒贡献者如何脱敏。

## Launch Copy（说人话，先讲痛点）

中文一句话版：

```text
买了代理不会配 Mac？把服务商后台那串参数粘贴进 Netfix，先检查能不能用，再一键开始使用；不用时也能恢复原来的网络设置。
```

中文 60 秒版：

```text
很多人买了代理，手机能用，Mac 却不会配。Netfix 是 macOS 上的本地小工具：
把服务商给你的 host:port:用户名:密码 粘贴进来，它先测试、再保存到钥匙串、最后由你确认是否开始使用。
连不上时，它会告诉你是地址抄错、节点挂了、账号失效，还是系统代理没切过去。
不需要 API Key，不上传密码，改网络前先备份，随时可恢复。
```

英文一句话版：

```text
Bought a proxy but can't configure your Mac? Paste the connection line into Netfix, let it precheck, save to Keychain, and start using it with one click — roll back anytime.
```

## Copy-Paste Launch Posts

发任何帖子都带同一个真实 case：

```text
https://github.com/baishiqi45-dotcom/netfix/blob/main/cases/2026-06-29-%E6%99%AE%E9%80%9A%E7%94%A8%E6%88%B7%E4%BB%A3%E7%90%86%E9%83%A8%E7%BD%B2%E4%BD%93%E9%AA%8C%E5%AE%A1%E6%9F%A5.md
```

### 中文传播文案 3 条

**1. 技术社区版（V2EX / 掘金 / NodeSeek）**

```text
【工具】做了个 macOS 本地网络自救小工具：粘贴代理参数 → 预检 → 一键使用

场景：买了代理，手机能用，Mac 不会配；或者 Codex/GitHub/ChatGPT 突然连不上，
不知道是 DNS、系统代理、节点挂了，还是账号失效。

Netfix 做的事：
• 粘贴 host:port:用户名:密码，先检查能不能连
• 保存到 macOS Keychain，密码不进日志
• 一键开始使用代理，改之前自动备份网络设置
• 出问题告诉你是哪一层，并给可恢复的下一步

当前是 v0.2.0-qa.1 未签名预览版，适合技术测试用户；README 里有 dry-run。
不卖代理、不内置节点、不承诺第三方服务质量。

求 star 和真实反馈：README 第一屏是否看得懂、安装是否可信、失败提示是否像人话。
```

**2. 普通用户版（即刻 / 小红书 / 朋友圈长图）**

```text
买了代理不会配 Mac 的姐妹/兄弟看过来 👀

我以前也是：服务商后台给了一串 host:port:用户名:密码，
完全不知道往 Mac 哪里贴，贴完也不知道有没有生效。

Netfix 把这个流程做成了三步：
1. 打开 App，粘贴服务商给的那一行
2. 点「检查并保存」
3. 检查通过点「开始使用代理」

它会在改系统设置前自动备份，不用了点「恢复原来的网络设置」就能还原。
密码只存在 Mac 钥匙串里，不上传。

现在还是 QA 测试版（未签名），首次打开需要在「系统设置 → 隐私与安全性」点「仍要打开」。
有兴趣可以去 GitHub 看看，觉得有用欢迎 star～
```

**3. GitHub star 召唤版（README 末尾 / Twitter/X 置顶）**

```text
Netfix — 买了代理不会配 Mac？粘贴服务商后台那串参数，先检查、再保存、一键使用；
不用时也能恢复原来的网络设置。

本地优先，不上传密码，不需要 API Key 也能诊断。
当前 QA 版未签名，适合技术测试用户试用。

如果它帮你定位过一次 Mac 网络问题，右上角点个 ⭐，
后续会跟进签名版、真实截图/动图和新 case。
```

---

Show HN title:

```text
Show HN: Netfix – local-first macOS network triage for AI/dev tool outages
```

Show HN body:

```text
I built Netfix after repeatedly seeing “Codex/GitHub/ChatGPT is unreachable” cases where the real issue was not the AI tool: it was DNS, system proxy, a dead proxy app, IPv6, TLS, or bad pasted proxy credentials.

Netfix is a local-first macOS app/CLI. It diagnoses the broken layer, explains the result in plain language, and only changes system proxy settings after explicit confirmation. If you already have HTTP/SOCKS5 proxy credentials, it can precheck, save to Keychain, apply, monitor, and restore the original network settings.

Current state: source-first MIT release. The QA DMG is unsigned/not notarized, so it is for technical testers; run --dry-run first. No telemetry, no proxy selling, no built-in nodes.
```

V2EX / NodeSeek title:

```text
做了个 macOS 本地网络自救工具：Codex / GitHub 连不上时先判断坏在哪一层，也能粘贴代理参数后预检、部署、恢复
```

V2EX / NodeSeek body:

```text
最近一直遇到一种很烦的问题：Mac 上 Codex、ChatGPT、GitHub 或 API 客户端突然连不上，普通用户看不出来是 DNS、系统代理、代理软件、IPv6、TLS、目标服务，还是自己粘贴的代理参数错了。

我做了一个开源小工具 Netfix。它的目标不是卖代理，也不是替代 Clash/Surge，而是在改系统配置前先诊断：哪一层坏了、下一步该点什么、改坏了怎么恢复。

如果你已经有 HTTP/SOCKS5 代理参数，可以在 App 里粘贴 host:port:用户名:密码，先检查能不能连，再保存到 Keychain，最后确认是否开始使用代理。当前 DMG 还是未签名 QA 版，适合技术测试用户；建议先跑 dry-run 或从源码看。

我最想要的反馈：README 第一屏是否看得懂、安装是否可信、代理参数入口是否清楚、失败提示是否像人话。觉得有用的话也欢迎 star。
```

Reddit short post:

```text
I built Netfix, a local-first macOS network triage app for AI/dev tool connectivity issues.

It tries to answer: is Codex/GitHub/ChatGPT failing because of DNS, system proxy, proxy software, IPv6, TLS, the target service, or pasted proxy credentials?

It can also precheck HTTP/SOCKS5 credentials, save them to Keychain, apply system proxy settings only after confirmation, and restore the original network settings.

Current state: MIT source-first release. The QA DMG is unsigned/not notarized, so treat it as technical testing and run --dry-run first. No telemetry, no built-in proxy nodes.
```

## Trust Claims — safe to assert

- local-first diagnosis (works offline)
- optional AI explanation after on-device redaction
- proxy credentials stored in macOS Keychain only
- every config-changing fix requires explicit user confirmation
- backup-and-restore for system network changes
- MIT license
- source-first: build from `git clone` and `pip install .`

## Claims — must NOT appear

- Netfix never claims guaranteed connectivity or guaranteed residential IP, and the docs must not promise any kind of third-party rule circumvention.
- No "DeepSeek 支持图片" / "DeepSeek is a vision model" — DeepSeek is text-only in this codebase.
- No "signed and notarized public DMG" before `release_preflight --with-dmg-smoke` actually passes Developer ID signing and notarization.
- No case quoting a real proxy URL, API key, QR code, cookie, or bearer token.

## How To Ask For Stars Without Begging

1. After the README change above, post the release on:
   - Hacker News (`Show HN`) with a one-paragraph problem statement, not a feature list.
   - r/macapps, r/MacOS, r/Proxifier (avoid rules-violating subs).
   - V2EX, NodeSeek, InfoQ CN — for the Chinese audience, with the Chinese README.
2. In every post, link to a **single concrete case** (`cases/2026-06-29-普通用户代理部署体验审查.md` is currently the strongest hook).
3. Do not promise what is not in the release. The current QA DMG is unsigned; say so out loud — credibility earns stars more than polish.
4. After 30 stars, write a follow-up post showing the **before / after** of a real diagnosis.

## 30-Star Sprint

| Step | Goal | Output |
|---|---|---|
| Day 1 | Make the repo trustworthy | GitHub About/topics set, README says unsigned QA plainly, dry-run comes before install |
| Day 2 | Show one real story | Link the ordinary-user proxy deployment case from README and every launch post |
| Day 3 | Post once in Chinese | V2EX / NodeSeek post with the same case link and no exaggerated claims |
| Day 4 | Collect friction | Turn the first 3 confusing comments into README fixes or issues |
| Day 5 | Post once in English | Reddit or Show HN only after the README first screen is stable |
| After 30 stars | Earn the follow-up | Publish a before/after diagnosis case and the next signed-DMG roadmap |

## Before Asking For Stars — verification

```bash
python3 -m pytest -q
python3 scripts/source_export.py --zip --json
python3 scripts/release_audit.py --scope workspace --root open-source-export/Netfix-0.2.0-source
python3 scripts/release_audit.py --scope workspace --root .
python3 scripts/release_preflight.py --with-dmg-smoke --json
python3 scripts/marketing_claims_check.py --json
```

Then manually check:

- README first screen renders both badges and hero image.
- README.en.md has no `<repo>` placeholder and the comparison table is above the fold.
- The one-line Codex MCP install works from a clean account through the raw `main` installer:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash`
- The one-line macOS app install works through the raw `main` installer, which downloads the `v0.2.0-qa.1` QA DMG:
  `curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash`
- GitHub Issues have safe templates and PR template covers architecture / schema impact.
- SECURITY.md gives a private-report path or a sanitized fallback.
- Release notes do not call an unsigned local build a public product.
