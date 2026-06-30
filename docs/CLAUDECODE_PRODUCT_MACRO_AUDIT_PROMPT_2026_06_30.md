# Claude Code 宏观产品冷审提示 - Netfix

你是 Claude Code。请在 `/Users/qibaishi/Desktop/网络` 里对 Netfix 做一次只读、对抗性、证据优先的宏观产品审计。

这不是代码格式检查，也不是泛泛夸奖。目标是判断：这个产品现在到底有没有产品力，普通小白用户能不能安装后直接用，代理部署链路是否真的闭环，技术实现哪里不对，前端交互哪里反人类，成熟度距离可交付还有多远。

## 产品背景

Netfix 目标不是网站，也不是给工程师看的命令行工具，而是一个本地 macOS 桌面软件。目标用户是不会命令行的普通用户：

- 买了住宅 IP / 数据中心代理 / 移动代理；
- 手里可能只有一行参数，例如 `host:port:username:password`；
- 想复制粘贴进去，让这台 Mac 能用代理上网；
- 出问题时希望软件告诉他“哪里坏了、怎么修、能不能一键修”，而不是看 DNS、Tier、root cause 这种工程术语；
- AI API 是增强能力，不应成为代理部署和基础诊断的前置条件。

不要使用真实代理凭据做测试。需要示例时只用：

```text
direct.example-proxy.test:8001:demo-user:demo-password
```

## 审计硬规则

1. 只读审计，除非另有明确授权，不要改文件、不要提交、不要删除任何东西。
2. 不要泄露、复述、扫描输出真实凭据。看到疑似代理配置、API key、token，只报告“存在敏感资料包/敏感字段风险”，不要摘录明文。
3. 所有判断必须给证据：文件路径、函数名、测试命令、构建命令、界面文本、流程节点。
4. 不接受“看起来不错”“建议优化体验”这种空话。每条问题必须说明：用户怎么被卡住、为什么会造成产品失败、最小修复动作是什么。
5. 不要只站在工程师视角。必须模拟一个完全不懂技术的目标用户。

## 必读材料

先读这些文件，再形成判断：

- `AGENTS.md`
- `docs/PROXY_DEPLOY_AUDIT_2026_06_29.md`
- `docs/PRODUCT_AUDIT_AND_ROADMAP_2026_06.md`
- `docs/RELEASE_CANDIDATE_SPRINT_2026_06_24.md`
- `docs/AIKB_PRODUCT_LANDING_RESEARCH_PROMPT_2026_06_29.md`
- `gui/macos/Sources/Views/DashboardView.swift`
- `gui/macos/Sources/Views/SettingsView.swift`
- `gui/macos/Sources/Views/ProxySetupView.swift`
- `gui/macos/Sources/APIClient.swift`
- `netfix/residential_proxy.py`
- `netfix/api.py`
- `tests/test_residential_proxy.py`
- `tests/test_api.py`
- `tests/test_macos_proxy_import_ui.py`
- `tests/test_macos_proxy_export_ui.py`

如果某个文件不存在，记录缺失，不要中断审计。

## 必须验证的核心问题

### 1. 一台新电脑能不能直接用

审计完整路径：

1. 用户拿到 `Netfix-0.2.0.dmg`；
2. 双击安装或拖进 Applications；
3. 打开 App；
4. 不打开终端；
5. 找到代理部署入口；
6. 粘贴一整行代理参数；
7. 预检；
8. 保存到本机；
9. 部署到这台 Mac；
10. 看到是否成功；
11. 出错时知道下一步怎么办；
12. 不用时能恢复原来的网络设置。

请判断这条路径是否真正闭环。不要只看有没有按钮，要判断用户是否知道自己该点什么、复制什么、每一步发生了什么。

### 2. 四段代理参数是否真的闭环

重点看这种输入：

```text
direct.example-proxy.test:8001:demo-user:demo-password
```

判断：

- 是否能识别为代理参数；
- 默认 HTTP 是否合理；
- SOCKS5 是否有清晰选择入口；
- 密码是否进入 Keychain；
- UI、日志、API 返回是否避免明文泄露；
- 保存、部署、监控、回滚是否被用户理解为不同动作；
- 如果认证 HTTP 需要本地桥接，用户是否知道 Netfix 必须保持打开。

### 3. AI 能力是否像产品，不像工程玩具

审计：

- AI API 配置入口是否显眼、好理解；
- 没接 API 时基础功能是否可用；
- 接 API 后用户能问什么，是否有聊天框/建议问题/上下文；
- 错误解释是否说人话；
- 是否有“看不懂诊断，让 AI 解释”的顺滑入口；
- 是否能把代理部署、健康监控、问题根因、修复建议串起来；
- 是否把 provider、model、base URL、Keychain 等概念暴露得过多。

### 4. 前端和交互是不是普通人爱用

从普通目标客户角度挑毛病：

- 首页第一屏是否直接告诉用户“我现在能干什么”；
- 代理部署入口是否足够明显；
- 文案是否有人话，是否还有 Tier、root cause、DNS 层、出口身份等术语污染；
- 状态卡是否真实有用，还是看起来像仪表盘摆设；
- 主按钮和下一步是否唯一、明确；
- 错误状态是否能直接带用户修复；
- 设置页是否过载；
- 是否有太多免责声明式文案；
- 是否能在 13 寸屏幕和普通窗口尺寸下舒服使用；
- 是否需要更好的 onboarding / wizard / checklist。

### 5. 技术正确性和成熟度

从 principal engineer 角度审计：

- macOS 系统代理写入、恢复、dry-run、rollback 是否安全；
- 认证 HTTP bridge 是否稳定，Netfix 退出后是否有明确处理；
- IPv6 关闭/恢复策略是否合理，哪些必须 dry-run 或用户确认；
- 后端 API 是否有清晰 schema 和错误码；
- Keychain 存储是否正确；
- 日志和报告是否脱敏；
- 测试是否覆盖真实用户路径，而不是只测底层函数；
- DMG / zip release 是否会夹带敏感文件；
- release audit 的 blocker 是否影响交付；
- 非 git 工作区、旧资料包、测试残留、后台进程等发布卫生问题是否存在；
- 是否有 crash、权限、签名、公证、首次打开 Gatekeeper 等真实安装风险。

## 建议运行的命令

能运行就运行，不能运行就说明原因。不要为了通过而隐藏失败。

```bash
pwd
ls -la
python3 -m pytest -q
cd gui/macos && swift build -c release
cd /Users/qibaishi/Desktop/网络 && python3 scripts/release_audit.py --json
cd /Users/qibaishi/Desktop/网络 && rg -n "Tier|root cause|DNS 层|出口身份|user123|pass456|real-secret|direct\\.miyaip|socks5h://[^\\s]+:[^\\s]+@|http://[^\\s]+:[^\\s]+@" gui/macos/Sources docs tests/test_macos_* || true
```

如果环境允许，再验证：

```bash
cd /Users/qibaishi/Desktop/网络
NETFIX_REQUIRE_BUNDLED_RUNTIME=true ./scripts/verify_dmg_backend.sh /Users/qibaishi/Desktop/网络/Netfix-0.2.0.dmg
```

## 输出格式

请输出一份中文审计报告，不要写客套话。结构必须如下：

### 0. 一句话判决

用一句人话判断：现在是“能给普通用户用了”“勉强能试用”“还不能交付”“产品方向不成立”中的哪一种，并说明最主要原因。

### 1. 成熟度评分

按 0-10 打分，每项给一句理由：

- 产品力
- 普通用户可用性
- 代理部署闭环
- AI 交互闭环
- 前端体验
- 技术可靠性
- 安全与隐私
- 发布交付成熟度

### 2. P0 / P1 / P2 问题清单

按严重程度排序。每条必须包含：

- 严重级别；
- 问题标题；
- 证据位置；
- 普通用户会怎么失败；
- 技术或产品根因；
- 最小修复动作；
- 验收标准。

### 3. 普通小白用户视角锐评

请用目标用户口吻直接说：

- 我第一眼看不看得懂；
- 我知不知道去哪里粘贴代理参数；
- 我知不知道复制什么；
- 我敢不敢点部署；
- 出错时我会不会放弃；
- 我会不会愿意继续用。

这部分要尖锐，但不要辱骂。

### 4. 顶级产品经理视角

回答：

- 核心价值主张是否清楚；
- 是否解决了真实痛点；
- 是否有“第一次成功”的路径；
- 哪些功能是假繁荣；
- 哪些入口应该砍、合并或前置；
- 下一轮最应该做的 5 个产品动作。

### 5. 顶级工程师视角

回答：

- 哪些实现最脆；
- 哪些抽象不对；
- 哪些风险会在线上放大；
- 哪些测试缺口最高危；
- 哪些日志/错误/状态机需要重构；
- 下一轮最应该做的 5 个工程动作。

### 6. 前端改造建议

给出具体 UI 改法：

- 首页第一屏应该怎么排；
- 代理部署 wizard 应该怎么走；
- AI 聊天入口怎么放；
- 设置页怎么降噪；
- 成功/失败/处理中状态怎么表达；
- 哪些文案必须改成人话，给出替换文案。

### 7. 是否值得继续做

明确回答：

- 这个产品方向是否成立；
- 如果成立，最短几步能变成用户愿意用的版本；
- 如果不成立，为什么；
- 现在距离“可以发给真实普通用户试用”还差什么。

### 8. 30 天落地路线图

不要大而空。按周列：

- 第 1 周必须修什么；
- 第 2 周必须打通什么；
- 第 3 周必须验证什么；
- 第 4 周必须交付什么；
- 每周的验收标准是什么。

## 关键要求

- 不要写“整体不错但仍需优化”。
- 不要输出泛泛设计原则。
- 不要只报测试结果。
- 不要只报代码问题。
- 要给出产品是否真的好用的判断。
- 如果产品现在仍然不适合小白用户，请直接说。
- 如果某些问题已被当前代码修掉，也要说明“已解决，但仍需验证真实用户是否理解”。

