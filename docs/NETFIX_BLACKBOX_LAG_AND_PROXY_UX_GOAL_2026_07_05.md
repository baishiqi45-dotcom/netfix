# Netfix 黑盒卡顿与代理管理产品 Goal

> 日期：2026-07-05  
> 输入：用户截图 4 张、用户真实案例、Claude/Kimi 只读冷审、当前 Netfix e47d166 代码状态。  
> 目标：为下一轮落地执行铺路，不把问题停留在“文案再人话一点”。

## 证据

- `docs/screenshots/2026-07-05-blackbox-lag/01-dashboard-proxy-saved.jpg`
- `docs/screenshots/2026-07-05-blackbox-lag/02-duplicate-proxy-list.jpg`
- `docs/screenshots/2026-07-05-blackbox-lag/03-diagnosis-and-duplicate-list.jpg`
- `docs/screenshots/2026-07-05-blackbox-lag/04-codex-ipv6-misdiagnosis.jpg`

本轮请注意：Kimi 的建议里有少量旧 `gui/web/index.html` 指向。当前主产品是 macOS Swift App，落地时以 `gui/macos/Sources/...` 为准，旧 web 前台不作为主入口。

## 核心判断

Netfix 现在已经比早期更像 App，但截图暴露了两个更深的问题：

1. **代理管理不是“用户资产管理”，而是“工程记录列表”。**  
   同一类 `proxy-socks5h` 重复出现，一屏七八条，每条都有“开始使用 / 更新参数 / 删除 / 更多操作”。普通用户不会觉得这是“历史记录”，只会觉得软件坏了。

2. **诊断仍停在“网络是否通 / 代理是否通”，没有覆盖“为什么卡”。**  
   用户真实案例是 Codex 卡死，最后发现百度网盘在上传。这个不应被看作某个个案，而应抽象为：本机或局域网被后台上传/同步/下载占满，导致实时交互类应用极慢。Netfix 目前没有把这类黑盒问题翻译成用户能执行的结论。

## P0 问题清单

1. 已保存代理列表重复、无合并、无当前/历史层级，截图里像坏数据。
2. 代理行按钮过多，用户不知道该点“开始使用”“更新参数”还是“删除”。
3. `未部署` 这类状态不够人话，应改成“还没用上 / 正在使用 / 最近检测失败”。
4. 首页三张状态卡仍像诊断摘要，不像“我现在卡不卡、谁在影响我”的答案。
5. `network_quality`、RTT、丢包等已有能力没有产品化成“速度 / 稳定 / 实时响应”。
6. 没有进程级上行/下行占用诊断，无法发现百度网盘、iCloud、Docker、下载器等后台占用。
7. Codex 卡顿时容易被误导到 IPv6、代理、API Key，而不是先判断“网络响应性被谁拖慢”。

## 产品抽象

不要把新能力叫“测速”。普通用户的问题不是“我有多少 Mbps”，而是：

- 现在为什么卡？
- 是代理慢，还是本机网络被占满？
- 是 Wi-Fi/路由器问题，还是某个 App 在后台上传？
- 我下一步该暂停哪个东西、切哪个代理、还是恢复网络设置？

建议产品能力命名：

- **实时响应检查**
- **网络被占满检查**
- **谁在占用网络**
- **卡顿原因排查**

## P0 落地路线

### P0-A：代理 Profile 去重和分组

目标：同一条代理重复粘贴 10 次，UI 不再增加 10 条。

后端：

- 在 `netfix/residential_proxy.py` 的 profile 中加入 `endpoint_fingerprint`。
- fingerprint 建议基于 `protocol | host | port | username`，不包含密码。
- `save_proxy_profile` 不再每次无条件生成新 UUID；如果 fingerprint 相同，更新原 profile 和 Keychain secret。
- 在 `netfix/settings.py` 增加按 fingerprint upsert/group 能力。
- 新增或扩展 API：
  - `GET /proxy/profiles/grouped`
  - `POST /proxy/profiles/cleanup-dupes`
  - `POST /proxy/profiles/<id>/rename`

前端：

- `gui/macos/Sources/Views/SettingsView.swift`
- 只突出：
  - 当前正在使用的代理
  - 最近保存的 1-3 条候选
  - 历史/重复记录默认折叠
- 每行最多两个显性操作：`使用这条`、`更多`。
- `删除`、`导出`、`验证` 放进菜单或折叠区。
- 如果检测到历史重复记录，出现一次性按钮：`合并重复代理`。

测试：

- `tests/test_residential_proxy.py`
  - 同一输入保存 10 次，只保留 1 个 fingerprint。
  - 密码变化时复用 profile id，但更新 Keychain。
- `tests/test_api.py`
  - grouped/cleanup/rename endpoint。
- Swift 字符串测试：
  - 不再默认出现大段 `proxy-socks5h-...` 标题。
  - 出现 `正在使用` / `还没用上` / `合并重复代理`。

### P0-B：首页增加“实时响应”静态卡

先不做后台常驻采样，先把已有诊断结果产品化。

后端已有：

- `netfix/layers/path.py` 的 `network_quality`
- `base_rtt_ms`
- `dl_throughput_kbps`
- `ul_throughput_kbps`
- `responsiveness_rpm`
- gateway ping/loss/rtt

前端：

- `gui/macos/Sources/Views/DashboardView.swift`
- 在状态卡区域新增/替换为：
  - **实时响应**：顺畅 / 偶尔卡 / 很卡
  - **延迟**：低 / 偏高 / 很高
  - **稳定性**：稳定 / 抖动 / 丢包
- 技术值可以在折叠详情里，首屏只说人话。

文案例子：

- `网络响应很慢，Codex、ChatGPT 这种实时应用会明显卡。`
- `延迟偏高，但没有检测到断网；可以先暂停后台上传或换一个代理节点。`
- `网络本身正常，问题更像是账号/API Key 或目标服务拒绝。`

### P0-C：新增“后台占用网络”只读诊断原型

目标：先做到“能发现疑似上传大户”，不是替代 Activity Monitor。

新增文件建议：

- `netfix/layers/bandwidth.py`
- 或 `netfix/bandwidth_hogs.py`

数据源候选：

- `nettop -P -x -l 1`
- `nettop -l 1 -k state`
- `lsof -i -P -n` 作为 fallback，只能提供连接，不提供速率。

识别对象：

- 百度网盘 / AliyunDrive / QuarkCloudDrive / OneDrive / Dropbox / iCloud
- WeChat / QQ / Feishu / DingTalk / Lark
- Docker / containerd / brew / softwareupdated
- Transmission / qBittorrent / 迅雷 / Motrix / aria2c

诊断输出：

```json
{
  "name": "bandwidth_hog",
  "status": "warn",
  "details": {
    "reason": "upload_saturated",
    "top_processes": [
      {"name": "BaiduNetdisk", "direction": "upload", "rate_kbps": 8500}
    ],
    "headline": "百度网盘正在上传，可能把 Codex 卡住了",
    "next_step": "先暂停百度网盘上传，再重新检查。"
  }
}
```

误判约束：

- 只在 `responsiveness_rpm` 低或 RTT 抖动明显时，把上传占用升级为问题。
- 视频会议、正常下载、测速不应直接报“卡顿根因”。
- 不展示 URL、远端 IP 明细、HTTP 内容。

### P0-D：黑盒卡顿优先级规则

修改：

- `netfix/reasoner.py`
- `netfix/explain.py`
- `netfix/user_facing_errors.py`
- `gui/macos/Sources/Models/UserFacingMessages.swift`

规则：

- 当 `bandwidth_hog=warn/fail` 且 `network_quality=warn/fail` 时，优先给出：
  `网络被后台上传/同步占满`
- 不要先把用户带到 IPv6、API Key、代理重置，除非证据更强。

示例人话：

- `不是断网，是你的网络被后台上传挤满了。`
- `检测到百度网盘正在上传，Codex 的请求可能在排队。暂停上传后再试。`
- `网络能通，但实时响应很差；这类问题常见于网盘、iCloud、Docker 或下载器在后台跑。`

## P1 路线

1. 后台轻量采样器：每 5-10 分钟采一次 `networkQuality`，异常时再采进程占用。
2. Dashboard “谁在占用网络”卡片：只显示 Top 3，不做全量进程表。
3. 卡顿事件时间线：最近 5 次“很卡”的时间和可能原因。
4. 代理健康趋势：最近 10 次延迟、失败率、认证失败。
5. 用户可给进程加白名单：比如视频会议期间不要报“上传占满”。

## P2 路线

1. Wi-Fi RSSI/SNR 趋势。
2. 路由器/网关拥塞识别。
3. 真实截图/GIF：展示“百度网盘上传导致 Codex 卡”的 before/after。
4. macOS 权限引导：解释为什么要读进程网络占用，默认本地不上传。

## 不做

- 不做 Activity Monitor 替代品。
- 不抓包，不解 TLS，不采集 URL 内容。
- 不做住宅 IP 质量评级、反封、防风控、节点推荐。
- 不自动执行 Tier 2 系统修复。
- 不让 LLM 自动替用户改系统网络。

## Claude Code 执行 Goal

```text
开启 goal：基于 Netfix 当前 main，完成一轮“代理管理去重 + 黑盒卡顿诊断设计落地”的 P0 产品升级。目标不是写报告，而是让截图里的两个核心问题不再出现：1) 设置页堆出大量重复代理；2) Codex/AI 卡顿时 Netfix 只会误导到 IPv6/API Key/代理，而不能识别后台上传占满。

项目路径：/Users/qibaishi/Desktop/网络

必须先读：
- docs/NETFIX_BLACKBOX_LAG_AND_PROXY_UX_GOAL_2026_07_05.md
- docs/PRODUCT_PLAIN_LANGUAGE_UX_AUDIT_2026_07_05.md
- gui/macos/Sources/Views/DashboardView.swift
- gui/macos/Sources/Views/SettingsView.swift
- gui/macos/Sources/Views/ProxySetupView.swift
- gui/macos/Sources/Models/UserFacingMessages.swift
- netfix/residential_proxy.py
- netfix/settings.py
- netfix/api.py
- netfix/layers/path.py
- netfix/reasoner.py
- netfix/explain.py
- netfix/user_facing_errors.py

证据截图：
- docs/screenshots/2026-07-05-blackbox-lag/01-dashboard-proxy-saved.jpg
- docs/screenshots/2026-07-05-blackbox-lag/02-duplicate-proxy-list.jpg
- docs/screenshots/2026-07-05-blackbox-lag/03-diagnosis-and-duplicate-list.jpg
- docs/screenshots/2026-07-05-blackbox-lag/04-codex-ipv6-misdiagnosis.jpg

第一步：
- git status / git diff，确认当前工作区。
- 不要覆盖别人改动。
- 先说明截图中最严重的 5 个问题。

P0-A 必须落地：代理 profile fingerprint 去重
- 同 protocol/host/port/username 视为同一条代理。
- 重复保存不再无限新增 profile。
- 密码变化时复用 profile id，更新 Keychain。
- 增加 grouped/cleanup/rename API 或等价最小能力。
- SettingsView 只突出当前代理和最近候选，重复历史默认折叠。

P0-B 必须落地：实时响应静态卡
- 把已有 network_quality/base_rtt/rpm/packet_loss 聚合成人话。
- Dashboard 不只显示网络/代理/目标网站，还要能说“现在很卡/偶尔卡/顺畅”。

P0-C 尽量落地最小版：后台占用网络诊断
- 新增 bandwidth_hog 或 upload_congestion 诊断。
- macOS 先用 nettop/lsof 做只读采样，失败时返回 unknown，不阻塞主诊断。
- 识别百度网盘、iCloud、OneDrive、Docker、下载器、系统更新等常见占用。
- 只输出进程名和方向/速率，不输出 URL/远端 IP/内容。

P0-D：根因优先级
- 当 network_quality 差 + bandwidth_hog 命中时，优先显示“网络被后台上传/同步占满”，不要先引导用户关闭 IPv6。

严格禁止：
- 不做 Activity Monitor 替代品。
- 不抓包、不解 TLS、不采集内容。
- 不做住宅 IP 评分、绕风控、防封、节点推荐。
- 不绕过 Tier 2 确认。

验收：
- 同一代理粘贴保存 10 次，profile 数不增长到 10。
- 旧重复数据能分组/合并/清理。
- Dashboard 能显示“实时响应”人话状态。
- 构造百度网盘上传 fixture 时，root cause 优先是 upload_congestion/bandwidth_hog。
- python3 -m pytest -q
- python3 -m py_compile netfix/*.py
- git diff --check
- cd gui/macos && swift build
- 如果改 UI，cd gui/macos && ./build_app.sh --install，并验证 /health + /dashboard/state。

最终交付：
- 改了哪些文件，每个文件解决哪个用户困惑。
- 测试结果。
- 还有哪些 P1/P2 未完成。
- 如果稳定，提交并推送 main。
```

## Kimi Code 执行 Goal

```text
开启 goal：站在中国普通 Mac 用户和国内代理购买者视角，对 Netfix 进行“代理管理混乱 + 黑盒卡顿诊断”专项落地。不要只写建议，能低风险改的直接改。

项目路径：/Users/qibaishi/Desktop/网络

必须先看：
- docs/NETFIX_BLACKBOX_LAG_AND_PROXY_UX_GOAL_2026_07_05.md
- docs/screenshots/2026-07-05-blackbox-lag/01-dashboard-proxy-saved.jpg
- docs/screenshots/2026-07-05-blackbox-lag/02-duplicate-proxy-list.jpg
- docs/screenshots/2026-07-05-blackbox-lag/03-diagnosis-and-duplicate-list.jpg
- docs/screenshots/2026-07-05-blackbox-lag/04-codex-ipv6-misdiagnosis.jpg
- gui/macos/Sources/Views/SettingsView.swift
- gui/macos/Sources/Views/DashboardView.swift
- netfix/residential_proxy.py
- netfix/settings.py
- netfix/reasoner.py
- netfix/explain.py

用户原话要吸收：
“代理那块很莫名其妙，咋这么多，乱七八糟；功能不完善，速度监控、稳定性、延迟这些基本的都没有；我之前 Codex 卡的要死，最后发现是百度网盘上传，取消上传立马好了。用户只知道好卡用不了，不可能自己想到原因。”

任务：
1. 先列出普通用户看截图最懵的 10 个点，必须具体。
2. 把代理列表从“重复工程列表”改成“当前代理 + 历史折叠 + 合并重复”。
3. 给所有代理状态改成人话：还没用上 / 正在使用 / 最近检测失败 / 需要重新输入密码。
4. 设计并尽量实现“网络被占满”诊断最小版。
5. 对百度网盘/iCloud/OneDrive/Docker/下载器后台上传这类场景给人话解释和下一步。
6. 不要碰旧 gui/web 作为主入口；当前主 UI 是 Swift macOS App。

验收：
- 一屏不再出现 7 条一模一样的 proxy-socks5h。
- 用户能一眼看出当前使用哪条代理。
- Dashboard 能说“实时响应差/可能被后台上传影响”。
- 测试和 swift build 通过。

禁止：
- 不卖代理，不宣传防封，不做住宅 IP 保证。
- 不做抓包，不做 Activity Monitor 替代。
- 不自动改系统设置。
```
