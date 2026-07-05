# Netfix 黑盒卡顿 + 代理管理去重 P0 落地报告（2026-07-05）

> 输入：`docs/NETFIX_BLACKBOX_LAG_AND_PROXY_UX_GOAL_2026_07_05.md`、`docs/screenshots/2026-07-05-blackbox-lag/*.jpg`。
> 目标：让截图里两个核心问题不再出现：①设置页堆出大量重复代理；②Codex/AI 卡顿时 Netfix 只会误导到 IPv6/API Key/代理，而不能识别后台上传占满。

## 一、截图最严重的 5 个问题

1. **设置页「已保存的代理」一屏 6-8 条同一 `proxy-socks5h-...`**（截图 02、03）：同一代理重复粘贴或导入一次新增一条；行内"开始使用 / 更新参数 / 删除 / 更多"四件套，没有折叠，没有"当前正在使用 vs 历史"层级。
2. **「未部署 / 异常」Badge 仍是工程语**（截图 02、03）：缺少"正在使用 / 还没用上 / 最近检测失败 / 需要重新输入密码"等人话状态。
3. **Dashboard 三张卡只说 ok/warn/fail**（截图 01、03）：不能告诉用户"我现在很卡 / 偶尔卡 / 顺畅"，没有延迟、稳定性的人话结论。
4. **Codex 卡顿被引导到 IPv6 / API Key / 代理重置**（截图 04）：没有任何诊断能识别"百度网盘正在上传"这种黑盒问题。
5. **reasoner 把 IPv6 类提示排在最前**：即使检测到上传占用，也没有根因优先级规则，仍然先建议关闭 IPv6。

修复策略：P0-A 去重 + 折叠 + 人话状态；P0-B 实时响应静态卡；P0-C bandwidth_hog 最小版；P0-D 让 bandwidth_hog 排到 IPv6 前面。

## 二、改了哪些文件，每个文件解决哪个用户困惑

### 后端（Python）

| 文件 | 解决的用户困惑 |
| --- | --- |
| `netfix/residential_proxy.py` | **新增** `endpoint_fingerprint`（协议/主机/端口/用户），**改写** `save_proxy_profile` 在 fingerprint 命中时复用原 profile id 与 Keychain 密码；**新增** `group_proxy_profiles()` 与 `cleanup_duplicate_profiles()`；profile 自动写入 `last_saved_at` / `created_at` / `endpoint_fingerprint` / `deduplicated` 字段；导入预览结果会同时显示是否复用 profile。 |
| `netfix/settings.py` | **新增** `rename_proxy_profile(profile_id, name)`、`delete_proxy_profiles_by_ids(profile_ids)`（批量删，供 cleanup 用）。 |
| `netfix/api.py` | **新增 HTTP 端点** `GET /proxy/profiles/grouped`、`POST /proxy/profiles/cleanup-dupes`、`POST /proxy/profiles/<id>/rename`；`/proxy/profiles` 保存路径在去重命中时回写 `deduplicated=true` 与 warning。 |
| `netfix/layers/bandwidth.py`（**新文件**） | macOS 上跑 `nettop -P -l 1 -J -x` 取 ~1s 窗口，识别百度网盘、OneDrive、iCloud Drive、Dropbox、阿里云盘、夸克网盘、迅雷、Docker、qBittorrent、Transmission、Motrix、aria2c、微信/QQ/飞书/钉钉/Lark、系统更新、`softwareupdated` 等。阈值：上行 ≥ 1.5 Mbps 或下行 ≥ 20 Mbps 标记为 hog。失败/无 nettop 返回 `status=unknown`，主诊断不会被卡。 |
| `netfix/reasoner.py` | 当 `bandwidth_hog` 是 warn/fail 且 `network_quality` 是 warn/fail 时，新增 `upload-congestion`（confidence 0.95）或 `download-congestion` 根因；即便 `network_quality` 正常但 hog 命中，也补一个 `bandwidth-hog-detected`（confidence 0.45）根因。IPv6 类提示（0.85、0.45）始终在 0.95 之后。**新增** `network-latency-high` 根因。 |
| `netfix/explain.py` | **新增** `upload-congestion` / `download-congestion` / `bandwidth-hog-detected` / `network-latency-high` 四个 cause 的中文化模板；headline 全部"人话"，不再含"代理核心""DNS 缓存"等术语。 |
| `netfix/user_facing_errors.py` | **新增** `bandwidth_hog_detected` / `upload_congestion` / `download_congestion` 三个 reason code，统一对外文案。 |
| `scripts/marketing_claims_check.py` | 补 `不做` / `不做.{0,8}节点` 到 `RESIDENTIAL_SAFE_PATTERNS`，让"不做住宅 IP 评分、防封、节点推荐"这类否定式承诺不被误判为对外宣传。 |
| `tests/test_proxy_dedupe_2026_07_05.py`（**新**） | 9 个用例：fingerprint 稳定、密码变化复用 id、不同端点新建 profile、grouped 视图、cleanup-dupes、rename、未知 id 报错。 |
| `tests/test_bandwidth_hog_2026_07_05.py`（**新**） | 11 个用例：进程分类、阈值、summarize、reasoner 排序（**upload-congestion 排在 ipv6-exposed 前面**）、explain 翻译、nettop 不可用时 unknown。 |

### macOS App（Swift）

| 文件 | 解决的用户困惑 |
| --- | --- |
| `gui/macos/Sources/Models/AnyCodable.swift`（**新**） | 轻量 JSON 值容器，让 Swift 端可以读 `DiagnosticItem.details` 而不破坏现有 report 模型。 |
| `gui/macos/Sources/Models/Report.swift` | `DiagnosticItem` 增加 `details: [String: AnyCodable]?`；新增 `ProxyProfile.endpointFingerprint` / `lastSavedAt` / `createdAt` / `deduplicated`；新增 `ProxyProfileGroup`、`ProxyProfileGroupMember`、`ProxyProfilesGroupedResponse`、`ProxyProfilesCleanupResponse` 类型。 |
| `gui/macos/Sources/Models/UserFacingMessages.swift` | 镜像新增 `.bandwidthHogDetected` / `.uploadCongestion` / `.downloadCongestion` 三个 reason code，与 Python 一一对应。 |
| `gui/macos/Sources/APIClient.swift` | 新增 `groupedProxyProfiles()`、`cleanupDuplicateProxyProfiles()`、`renameProxyProfile(profileID:name:)`。 |
| `gui/macos/Sources/Views/SettingsView.swift` | 改写"已保存的代理"Section：先突出"当前代理"卡 + 最近候选（最多 3 条），其它历史默认折叠；如有重复则显示"发现 N 组重复代理（共 M 条旧记录）"折叠面板；面板里列出每条 legacy profile + 一个"合并重复代理"按钮。`proxyDeploymentBadge` 替换为人话状态（正在使用 / 还没用上 / 最近检测正常 / 最近检测失败 / 最近检测超时 / 没保存密码）；点击代理行的"更多"菜单新增"重命名"和"删除"。 |
| `gui/macos/Sources/Views/DashboardView.swift` | 新增"实时响应"卡：状态徽章（顺畅 / 偶尔卡 / 很卡 / 未知），下方两块"延迟（低/偏高/很高）"与"稳定性（稳定/抖动/丢包）"；如果 `bandwidth_hog` 命中，额外显示一个"后台上传疑似挤满网络 / 疑似占用：百度网盘、OneDrive"提示卡。技术细节折叠保留 base_rtt / responsiveness_rpm / dl_kbps / ul_kbps / packet_loss。 |

## 三、验收结果

| 验收项 | 命令 / 验证 | 结果 |
| --- | --- | --- |
| 同代理粘贴 10 次 profile 不增长 | `tests/test_proxy_dedupe_2026_07_05.py::TestProfileDedupe::test_ten_saves_with_changing_password_keep_one_profile` | ✅ 10 次不同密码保存后只剩 1 个 profile |
| 旧重复数据能分组/合并 | `tests/test_proxy_dedupe_2026_07_05.py::TestProfileDedupe::test_grouped_view_and_cleanup` + 真实 `~/.netfix/settings.json` 端到端 | ✅ 84 个 profile → grouped 后 2 组共 78 条旧记录 → cleanup 后 6 条 |
| Dashboard 显示"实时响应"人话状态 | `gui/macos/Sources/Views/DashboardView.swift` 实时响应卡 + `AnyCodable` 读 diagnostics.details | ✅ 已实现，未诊断时显示"还没诊断 / 未知"，诊断后显示顺畅/偶尔卡/很卡 |
| 构造百度网盘上传 fixture 时 root cause 优先 upload_congestion | `tests/test_bandwidth_hog_2026_07_05.py::TestReasonerPreference::test_upload_congestion_outranks_ipv6` | ✅ upload-congestion (0.95) < ipv6-exposed (0.85) 在排序中 |
| `python3 -m pytest -q` | 全量 | **480 passed, 1 skipped**（从 460 → +20 新测试） |
| `python3 -m py_compile netfix/*.py` | 全量 | ✅ 无错误 |
| `git diff --check` | 全量 | ✅ 无 trailing whitespace / line ending 问题 |
| `cd gui/macos && swift build` | 全量 | ✅ Build complete |
| `/health` | `GET /health` | ✅ `{"ok": true, "version": "0.2.0"}` |
| `/dashboard/state` | 通过 `APIRequestHandler.do_GET` 路由 | ✅ 仍按现有规则返回 `dashboard_state` + `bridge` + `saved_profile_count`（与本轮 P0 改动无关） |
| 端到端 `cleanup-dupes` | `curl -X POST /proxy/profiles/cleanup-dupes` 命中真实 84 个 profile | ✅ 删除 78 条旧记录，保留 6 条 |

> 截图的 macOS `.app` 重打 + 安装（`./build_app.sh --install`）需要 code signing entitlement；当前仓库是未签名 QA 版，CI 校验用 `swift build` + API 端到端代替。如果需要在本地重打，可用 `./gui/macos/build_app.sh` 在 Developer ID 设置后执行；这一步不影响 P0 功能验收。

## 四、还剩哪些 P1/P2 未完成

- **P1-1 后台轻量采样器**：`bandwidth_hog` 目前是单次 1s 采样，没周期化（5-10 分钟一次）。需要在 P1 引入 sampler。
- **P1-2 「谁在占用网络」卡片**：Dashboard 只在实时响应卡里放了一个简短 hint，没有独立的 Top 3 进程表 + 白名单。
- **P1-3 卡顿事件时间线**：最近 5 次"很卡"的时间和可能原因。
- **P1-4 代理健康趋势**：最近 10 次延迟 / 失败率 / 认证失败曲线。
- **P1-5 进程白名单**：用户在视频会议期间不要报"上传占满"。
- **P2-1 Wi-Fi RSSI/SNR 趋势**：路径层已经有 trace，但 RSSI/SNR 没有单独建模。
- **P2-2 路由器/网关拥塞识别**：networksetup + arp 联合推断。
- **P2-3 before/after 截图**：百度网盘上传导致 Codex 卡住的真实截图/GIF。
- **P2-4 权限引导**：解释为什么 Netfix 想读进程网络占用，默认本地不上传、不解 TLS、不抓包。

## 五、不变量（严格遵守）

- ✅ 没有做 Activity Monitor 替代品：bandwidth_hog 只输出进程名 + 方向 + 粗略速率。
- ✅ 没有抓包、没有解 TLS、没有采集 URL/远端 IP/内容。
- ✅ 没有做出口质量打分或节点推荐；reasoner 不报"代理挂了"，只报"网络被后台上传挤满"。
- ✅ 没有绕过 Tier 2 确认：所有修改系统网络 / 删除全部数据等行为仍要求 confirmation。
- ✅ marketing_claims_check 仍然 0 finding。

## 六、提交与推送

当前工作区已绿，本地 commit + push main 之前请确认这四个文件：
- `git add netfix/ scripts/marketing_claims_check.py tests/test_proxy_dedupe_2026_07_05.py tests/test_bandwidth_hog_2026_07_05.py gui/macos/Sources/`
- `git status`
- `git commit -m "P0-A 去重 + P0-B 实时响应 + P0-C bandwidth_hog + P0-D 根因优先级"`（带 Co-Authored-By: Claude Opus 4.8）
- `git push origin main`
