# Netfix 宏观产品力 & 开源 Star 转化审计
> 审计日期：2026-07-01
> 范围：`<repo>`（commit dbbd113 之后的 working tree）
> 立场：陌生 GitHub 用户视角 + 工程师落地视角
> 语气：尖锐，工程上可执行

---

## 0. 总体判断

Netfix 已经做完了 **80% 的工程**，但只完成了 **30% 的开源传播**。

工程侧是真的硬：本地优先诊断、Tier 1/2/3 修复分级、Keychain + networksetup 备份回滚、MCP stdio 服务、HTTP API、release_audit/release_preflight/source_export 三件套、Source-export 排除敏感文件、proxy_bridge 真桥接、redaction 在 LLM 上传前先脱敏——这套在中文开源工具里属于"认真做事"的那一档。

但**对陌生 GitHub 访客**而言，今天的 Netfix 看上去像一个"工程师给自己写的诊断脚本"：

1. **首屏 5 秒测试失败**：README 折叠前没有把"它解决什么 / 它是 App 还是 CLI / 一行安装 / 跟谁不同"四件事讲清楚，要往下翻 80 行才看到 `curl | bash`。
2. **没有真实 App 截图**：`assets/github/` 只有概念 hero 图和流程图，0 张 App 真机截图、0 个 GIF、0 个对比图。
3. **没有竞品对比**：Topics 里塞了 `clash` / `mihomo` / `sing-box`，README 通篇没解释 Netfix 跟这些的关系，搜竞品词进来的用户直接跳出。
4. **Topics 选词失焦**：2026 年开发者最常搜的 `claude` / `cursor` / `kimi` / `mcp` / `homebrew` 一个没占位。
5. **MCP 实际只对 Codex CLI 完整工作**：Kimi/Claude/Cursor 用户拿到的是一段"请自己手填"提示，开箱体验打折。
6. **关键安全/工程漏洞**包括：MCP 通道绕过 Tier 2 confirmation magic word、`netfix_proxy_switch` 不脱敏 `_secret`、`logs.append_event` 完全不脱敏、`safety.classify_command` 用子串匹配（`pseudocode` 假阳性，`osascript -e` 漏判）、bridge `_tunnel` 无 wall-clock 上限、Keychain -T 在开发模式不生效等。
7. **CI 软门禁**：唯一的 workflow 只跑一个 `macos-latest`，不跑 `release_preflight`、不跑 `verify_dmg_backend`、不强制 branch protection。

**好消息**：所有发现的"必须改"中，**80% 是文案和脚本安全姿势**，**没有任何一条**触及核心诊断/修复引擎的正确性。

---

## 1. 陌生用户 5 秒测试

| 心里想问 | README 给的（修改前） | 评分 |
|---|---|---|
| 它解决什么 | "local-first macOS network triage tool for AI and developer workflows" — 黑话堆叠 | 半懂 |
| App 还是 CLI | 折叠前一字未提，要翻 80 行才看到 `python3 netfix.py ...` 和 `Netfix.app` | 失败 |
| 一行安装 | 折叠前**没有**，"现在能怎么用"小标题下才给两段 `curl | bash` | 失败 |
| 跟 ClashX / Surge / Shadowrocket / sing-box 区别 | 通篇**完全不对比** | 失败 |
| 跑起来什么样 | 一张 1280×360 流程图，**无 App 截图、无终端截图、无对比表** | 失败 |

**本次已修**（见末尾"已落地的修补"）：README.md / README.en.md 顶部加了"它做什么 / 60 秒开始 / 跟现有工具比 / 它不做什么"四段首屏承诺，并把"Real cases 速览"放在显眼位置。

---

## 2. 普通用户 6 个问题测试

| 问题 | 结论 |
|---|---|
| 这是 App 还是 CLI？ | README 改了之后：顶部 60 秒段明示"一行 macOS App / 一行 MCP / 源码装"三种入口。 |
| 怎么安装？ | 两行 `curl | bash`，同时承认 QA DMG 未签名。**已修**。 |
| 代理参数从哪里来？ | "代理到底复制什么"段 + examples（`socks5h://`、`http://`、`host:port:user:pass`）。**已存在**。 |
| 什么能一键部署，什么必须确认？ | "安全边界" + AGENTS.md 的 Tier 1/2/3 说明。**已存在**，但建议 README 再加一行醒目提示。 |
| AI API Key 是可选还是必须？ | "AI 问答怎么接"段第一句"不接 API 也能用"。**已存在**。 |
| 出问题怎么恢复？ | "安全回滚"功能行 + `proxy_apply_journal.json` + README `rollback` 段。**已存在**但需要在 README 顶部"它不做什么"段之后加一行 "改坏网络能回滚"。 |

**残留 gap**：README 没直接告诉普通用户"如果在 macOS 上看到『无法验证开发者』弹窗该怎么点"。这是 QA 未签名 DMG 阶段最常见的 1 分钟卡点。**建议在 README.en.md / README.md 的"60 秒开始"段下加一个"First launch: System Settings → Privacy & Security → Open Anyway"提示。**

---

## 3. 技术链路审计

### 3.1 一行安装脚本（`scripts/install_mac_app_from_github.sh`）

| 项 | 状态 | 文件:行 | 改法 |
|---|---|---|---|
| `set -euo pipefail` | ✅ | install_mac_app_from_github.sh:3 | 保留 |
| `IFS` 重置 | ❌ | 同上 | 加 `IFS=$'\n\t'` 防 word-split |
| DMG SHA256 默认值硬编码 | ✅ | line 8 | 保留但**不要让环境变量** `NETFIX_DMG_SHA256` 完全旁路——加"环境变量必须与内置一致"校验 |
| `~/Applications` 路径 race | ⚠️ | line 16, 109 | 升级为 atomic rename（先写到 `.partial`，再 `mv`） |
| Gatekeeper 提示说明 | ✅ | line 38, 145 | 但应在 `open` 之前 echo 一遍 |
| 失败回滚（半残 Netfix.app / 半残 backup） | ⚠️ | 全文件 | 加 `rollback()` 函数：first-time 失败时把 backup 移回 |
| `curl` 用 `-fsSL` | ⚠️ | line 87 | 改 `curl -fL` 已经有 fail，缺 silent mode |
| 没有 audit 日志 | ❌ | 全文件 | 加 `logger -t netfix-installer "msg"` 让 QA 出问题可溯源 |
| `curl pipe bash` 自身无签名 | ❌ | usage | README/STAR_GUIDE 显式提示"首次运行请先 `curl -fsSL ... | less` 审一遍" |

### 3.2 MCP 安装脚本（`scripts/install_codex_mcp_from_github.sh`）

| 项 | 状态 | 改法 |
|---|---|---|
| `mcp_server.py` 路径引号转义 | ⚠️ line 118 | 改写 `~/.codex/config.toml` 而不是依赖 `codex mcp add` 的 shell 解析 |
| 临时目录清理 | ✅ | 保留 |
| 升级 backup 累积 | ❌ | 加 `max_backups=3` 滚动 |
| 缺 `--uninstall` / `--revert` | ❌ | 加 |
| source zip 无签名校验 | ❌ | 至少校验 `mcp_server.py` 的 `sha256`，SHA 跟 release 一起发 |
| zip-slip 防护 | ✅ | 保留 |

### 3.3 MCP server（`netfix/mcp_server.py`）

| 问题 | 文件:行 | 改法 |
|---|---|---|
| 30 个工具命名一致 `netfix_xxx` | ✅ | 保留 |
| `netfix_fix_issue` 跳过 Tier 2 confirmation magic word | mcp_server.py:433-446 | **必须改**：对齐 api.py `_execute_confirmed_fix` 的 `SYSTEM_FIX_CONFIRMATION` 协议；`netfix_fix_issue` 对 Tier 2 必须 dry-run → 二次确认 |
| `netfix_proxy_switch` 不脱敏 `_secret` 字段 | mcp_server.py:450-457 + cli.py:862-868 | **必须改**：MCP 出口套 `_strip_internal_secrets(result)`，复用 `api.py:818-828` |
| `agent_tools` 工具 return 原始 stderr，可能带明文 proxy 凭证 | agent_tools.py:39, 199, 222, 240, 295 | **必须改**：加 `_safe_stderr(s, max_len=200)` helper，先正则 `://[^@]+@` 替换为 `***@` |
| `netfix_get_global_state` 硬编码 `"platform": "darwin"` | agent_tools.py:113 | **必须改**：返回 `platform.system().lower()`；加 Linux/Windows fallback 探针 |
| schema 信息量低：没 output schema、没 fix 列表发现、没元查询 | mcp_server.py:73-86, 64-72 | **应该改**：加 `netfix_list_fixes` 返回可用 fix id + tier + 描述；`issue` 字段用 `oneOf` 给出 enum |
| stdio server 无超时与信号处理 | mcp_server.py:522-549 | **应该改**：用 `concurrent.futures.ThreadPoolExecutor`；注册 SIGINT/SIGTERM graceful shutdown |
| 协议版本固化在 `2024-11-05` | mcp_server.py:495 | **应该改**：客户端 initialize 协商时按 client 版本回应；至少加一个 `sse`/`streamable-http` 模块 |
| Kimi/Claude/Cursor 实际注册 | scripts/install_mcp.sh:88-98 | **应该改**：补 `--claude-desktop`（`~/Library/Application Support/Claude/claude_desktop_config.json`）、`--cursor`（`~/.cursor/mcp.json`）分支；Kimi 尝试探测 `~/.kimi/mcp.json` |

### 3.4 Release / SHA / preflight / CI

| 检查 | 状态 | 改法 |
|---|---|---|
| `release_preflight.py` 串 8 项检查 | ✅ | 保留 |
| `release_audit.py` 工作区 secret 扫描 | ✅ | 保留 |
| `source_export.py` 排除敏感目录 | ✅ | 保留 |
| DMG SHA256 校验 | ✅ verify-download.py | 保留 |
| `path_sanitizer` 全覆盖 | ❌ | `source_export.py` 写 `SOURCE-EXPORT-MANIFEST.json` 时不 sanitize `audit_findings.path`；`clean_machine_qa.py` 写 `clean-machine-qa.json` 时不 sanitize `artifact.release_manifest/dmg`。**必须改**。 |
| `release_gate.sh` 被 CI 调用 | ❌ .github/workflows/ci.yml | **必须改**：加一个 `release-gate` job，至少跑 `release_audit + release_preflight`；或者在 `app` job 里挂 `--require-runtime` |
| macOS 矩阵 | ❌ | ci.yml:11-13 只有 `macos-latest`。**必须改**：加 `macos-14 / macos-15 / macos-26` 矩阵 |
| DMG smoke 跑不跑 | ❌ | ci.yml `app` job 只跑 `swift build` + `release_audit --scope bundle`。**必须改**：加 `verify_dmg_backend.sh`（opt-in 标记）或 `release_preflight --with-dmg-smoke` |
| 失败是否能强制 block PR merge | ❌ | 没有 branch protection 写到 workflow。**应该改**：在 repo Settings 配 required check `ci / pytest` |
| `make test` vs CI `pytest` 跑两套 runner | ⚠️ Makefile:19-20 | 统一用 pytest |

### 3.5 macOS 网络配置 / 代理桥 / Keychain / 回滚

| 问题 | 文件:行 | 改法 |
|---|---|---|
| `proxy_bridge.py` 真的安全（密码入 Keychain、备份原网络、失败回滚） | ✅ 整体 | 保留 |
| `keychain.is_available()` 不过滤 macOS 版本 | keychain.py:17-19 | 加 `platform.mac_ver()[0]` 比较；Tahoe 上要求 Advanced Data Protection 兼容 |
| `keychain.add_generic_password -T` 用 `sys.executable` | keychain.py:23-25 | dev 模式（未 frozen）时**不传 -T**，fallback `-A`（每次问） |
| `_run_networksetup` 第一个失败就停 | residential_proxy.py:848-852 | **必须改**：循环内 `try/except` 累计结果，web+secure+socks 三项必须都 ok 才继续 |
| IPv6 不可还原时静默跳过 | residential_proxy.py:817-821 | 备份阶段 `mode=unknown` 主动 raise 阻止应用 |
| `redaction._redact_value` 不脱敏 `last_check` / `identity_report` | redaction.py:138-164 | 扩 `RAW_DROP_KEYS` 或在 strict 模式整块 drop |
| `safety.classify_command` 关键字子串匹配 | safety.py:71 | 用 `\b(sudo|networksetup|pfctl|...)\b` 词边界；补 `osascript ... with administrator privileges` 黑名单 |
| `bridge._tunnel` 300 秒超时 | proxy_bridge.py:362 | 加 wall-clock 60s 上限 |
| `bridge` 默认 `127.0.0.1` 但 macOS IPv6 `::1` 仍可达 | proxy_bridge.py:391 | `address_family = socket.AF_INET` 强制 IPv4 |
| `apply_proxy_profile` 把 `auto_proxy_url` 明文写 journal | residential_proxy.py:1965-1991 | 写 journal 前 drop `auto_proxy_url` 整个字段 |
| `proxy_monitor_service` 每跑一次就 upsert settings.json | proxy_monitor_service.py:166 | 监控只写 `last_check` 子字段，差异写盘 |
| `proxy_bridge.start_http_bridge` 没设 `request_timeout` | proxy_bridge.py:222, 270 | 加 60s wall-clock |
| `redaction._redact_string` URL_RE 不覆盖 `socks5://` 文本 | redaction.py:102-105 | `URL_RE` 扩到 `socks5?` 协议 |
| `logs.append_event` 完全不脱敏 | logs.py:89-99 | **必须改**：写盘前 `redaction.redact_report(event, level="balanced")` |
| `_bridge_server` 进程崩溃 = 监控死，桥接端口仍被系统代理指 | proxy_bridge.py + residential_proxy.py:2095 | App 启动时 `restore_from_settings` + `recover_stale_bridge` 已经存在；README/App 要提示用户"App 退出会停监控" |
| `residential_proxy.py` 2483 行/98KB | residential_proxy.py | **应该改**：把 `audit_proxy_identity` / `export_client_profile` / `proxy_monitor_service` 拆到三个独立模块 |

---

## 4. 产品创新 vs 命令包装

| 维度 | 现状 | 评价 |
|---|---|---|
| `--json` 全局 + JSON 输出 | ✅ | 不是创新，是**基线** |
| `last_report.json` 持久化 | ✅ | 是创新点：agent 可 `cat` 拿报告 |
| MCP server | ✅ 30 工具 | 是创新点，但 schema 信息密度不够、缺 fix 列表发现、缺 output schema |
| LLM 上传前脱敏 + LLM 输出后再次脱敏 | ✅ llm_explain.py:127-167 | **真正的产品创新**：把 LLM 降级为"文案生成器" |
| `safe_action_map` 本地 allowlist | ✅ llm_explain.py:98-120 | **真正的产品创新**：LLM 输出 action id 必须先过本地白名单 |
| `proxy_switch` 按"是否可逆"切 tier | ✅ cli.py:835-859 | 有产品直觉 |
| `redaction_audit` + `redacted_report_hash` | ✅ llm_explain.py:92-95 | agent 可审计脱敏覆盖 |
| 反向通道：用户告诉 netfix "我试过 X 别再建议" | ❌ | **缺**，是真正的 agent-native 创新空间 |
| `reasoner` 缺 evidence 链 | ⚠️ reasoner.py:31-54 | **必须改**：root_cause 加 `evidence: [{diagnostic, status, weight}]`，UI 可展示 |
| streaming / 增量输出 | ❌ | **可以改**：agent 体验加分 |
| 自动 planner（"根据上一次结果决定下一步"） | ❌ | **可以改** |
| agent 反向反馈环 | ❌ | **可以改** |

**结论**：Netfix **不是**"命令包装器"，但**也还不是**"agent-native 产品"。它有所有原料（结构化输出 + MCP + LLM 安全 + 本地 allowlist），**缺的是把原料拼成"让 Agent 真的能自主决策"的最后一公里**。

---

## 5. 增长素材审计

| 检查 | 现状 | 改法 |
|---|---|---|
| 首屏价值主张 | ❌ | **已修** |
| 一键安装按钮 | ⚠️ 不在折叠前 | **已修**：README 顶部 "60 秒开始" 段 |
| 竞品对比表 | ❌ | **已修**：4 行对比表 |
| Real cases | ❌ | **已修**：3 条案例链接 |
| App 真机截图 | ❌ 0 张 | **必须改**：`assets/github/zh/` + `assets/github/en/` 各 6+ 张（启动空态 / 诊断完成页 / 代理粘贴 / 预检结果 / 部署成功 / 失败 plain-language 截图） |
| GIF 动图 | ❌ 0 个 | **应该改**：8 秒内 diagnose / explain / fix / restore 各 1 个 |
| 终端 `codex --json` 截图 | ❌ 0 张 | **应该改**：1 张，方便开发者人群 |
| 社交证明 | ❌ | **可以改**：等真实用户案例再补；当前用"cases/2026-06-29-普通用户代理部署体验审查"做引子 |
| Logo / Favicon | ❌ | **应该改**：在 hero.svg 基础上做圆角方形 mark |
| Topics | ⚠️ 19 个偏工程师 | **已修**：换成 30 个，加 `claude` / `cursor` / `kimi` / `mcp` / `homebrew` / `apple-silicon` / `model-context-protocol` |
| Release notes 写给开发者 | ❌ | **已修**：写给最终用户，三段式（What changed / Try it / Known limits） |
| `marketing_claims_check.py` 通过 | ✅ | 已修文案后跑过；新增的 case 在 safe 边界内 |

---

## 6. 优先级总表

### 6.1 必须改（不改不能 Star）

1. **首屏 5 秒价值主张** — `README.md` / `README.en.md` 顶部
   - **状态：已落地**
2. **Topics 重排** — `.github/repository.yml`
   - **状态：已落地**
3. **Real cases 段 + 竞品对比表** — `README.md` / `README.en.md`
   - **状态：已落地**
4. **PR 模板补全**（架构 / 输出 schema / 链接 issue） — `.github/PULL_REQUEST_TEMPLATE.md`
   - **状态：已落地**
5. **Release notes 写给用户** — `docs/github/RELEASE_NOTES_V0.2.0.md`
   - **状态：已落地**
6. **STAR_GUIDE 加上竞品对比 + 社交证明清单** — `docs/github/STAR_GUIDE.md`
   - **状态：已落地**
7. **CI 加 `release_preflight` / DMG smoke** — `.github/workflows/ci.yml`
   - **状态：未做**，写入 7 天冲刺 Day 2
8. **MCP `netfix_fix_issue` 强制 Tier 2 confirmation magic word** — `netfix/mcp_server.py:433-446`
   - **状态：未做**，写入 Day 3
9. **`logs.append_event` 加 redact** — `netfix/logs.py:89-99`
   - **状态：未做**，写入 Day 3
10. **macOS CI 矩阵（14/15/26）** — `.github/workflows/ci.yml`
    - **状态：未做**，写入 Day 4

### 6.2 应该改（漏掉会一直少 Star / 少可信度）

11. App 真实截图 6+ 张
12. GIF 动图 1-4 个
13. MCP `netfix_list_fixes` 工具 + `issue` 字段 enum
14. `agent_tools` stderr `_safe_stderr` helper
15. `safety.classify_command` 用词边界 + 补 `osascript` 黑名单
16. `keychain.add_generic_password -T` dev 模式禁用
17. `proxy_bridge._tunnel` 60s wall-clock
18. `bridge` 强制 `socket.AF_INET`
19. `_run_networksetup` 第一个失败就停 → 改为累计
20. `path_sanitizer` 在 `source_export.py` / `clean_machine_qa.py` 也调用
21. `release_gate.sh` 进 CI
22. `residential_proxy.py` 拆分

### 6.3 可以改（锦上添花）

23. Logo / Favicon / social preview
24. `netfix_kb_topics` 工具
25. `explanation` 字段加 reasoning trace
26. streaming 增量输出
27. 反向通道：用户标记 "我试过 X 别再建议"
28. 自动 planner

---

## 7. 文件级落地清单（按 ROI 排序）

| # | 文件 | 改什么 | 为什么 |
|---|---|---|---|
| 1 | `README.md` / `README.en.md` 顶部 | 加 4 段首屏承诺 + 竞品对比 + Real cases | 已修 |
| 2 | `.github/repository.yml` | 重排 topics（30 个，覆盖 2026 搜索词） | 已修 |
| 3 | `.github/PULL_REQUEST_TEMPLATE.md` | 加 Architecture / Affected Areas / Output Schema Impact | 已修 |
| 4 | `docs/github/RELEASE_NOTES_V0.2.0.md` | 重写为用户向 | 已修 |
| 5 | `docs/github/STAR_GUIDE.md` | 加竞品对比 / 社交证明清单 / 转化话术 | 已修 |
| 6 | `netfix/mcp_server.py:433-446` | `netfix_fix_issue` 对齐 `SYSTEM_FIX_CONFIRMATION` | 安全 |
| 7 | `netfix/mcp_server.py:73-86` | 加 `netfix_list_fixes` + `issue` 字段 enum | agent 体验 |
| 8 | `netfix/logs.py:89-99` | `append_event` 写盘前 `redact_report` | 安全 |
| 9 | `netfix/agent_tools.py` 多处 | `_safe_stderr` helper 脱敏 | 安全 |
| 10 | `netfix/safety.py:71` | 用 `\b` 词边界；补 `osascript -e` 黑名单 | 安全 |
| 11 | `netfix/proxy_bridge.py:362` | wall-clock 60s | 安全 |
| 12 | `netfix/proxy_bridge.py:_BridgeServer` | 强制 `socket.AF_INET` | 安全 |
| 13 | `netfix/residential_proxy.py:848-852` | `_run_networksetup` 累计结果 | 安全 |
| 14 | `netfix/keychain.py:23-25` | dev 模式禁用 `-T` | 安全 |
| 15 | `netfix/residential_proxy.py:1965-1991` | 写 journal 前 drop `auto_proxy_url` | 安全 |
| 16 | `netfix/reasoner.py:31-54` | root_cause 加 `evidence` 链 | agent-native 创新 |
| 17 | `netfix/cores/` 五个适配器 | 加 JSON Schema + lint | 工程质量 |
| 18 | `scripts/source_export.py` | `SOURCE-EXPORT-MANIFEST.json` sanitize path | 安全 |
| 19 | `scripts/clean_machine_qa.py` | 写 `clean-machine-qa.json` sanitize | 安全 |
| 20 | `.github/workflows/ci.yml` | macOS 矩阵 + release_preflight + verify_dmg_backend | 门禁 |
| 21 | `scripts/install_mcp.sh` | 加 `--claude-desktop` / `--cursor` | 增长 |
| 22 | `scripts/install_mac_app_from_github.sh` | atomic rename + 滚动 backup + `IFS` + `logger` | 工程 |
| 23 | `assets/github/zh/` / `en/` | 真实截图 6+ 张 | 增长 |
| 24 | `assets/github/...` | 1-4 个 GIF | 增长 |
| 25 | `pyproject.toml` | 加 `[project.optional-dependencies] dev` | 工程 |

---

## 8. 7 天冲刺计划

> 目标："让陌生 GitHub 用户更愿意点 Star 和试用"
> 节奏：每天 1-2 个**交付物**，每条交付物可被 1 个 PR 完成

### Day 1（已落地） — **README 5 秒承诺 + Topics + 模板 + Release notes**

- [x] `README.md` / `README.en.md` 顶部 4 段：它做什么 / 60 秒开始 / 跟现有工具比 / 它不做什么
- [x] `README.md` / `README.en.md` 加 "Real cases 速览" 段，引用 3 个 case
- [x] `.github/repository.yml` topics 重排到 30 个
- [x] `.github/PULL_REQUEST_TEMPLATE.md` 补全架构 / 输出 schema / 链接 issue
- [x] `docs/github/RELEASE_NOTES_V0.2.0.md` 重写为用户向
- [x] `docs/github/STAR_GUIDE.md` 加竞品对比 / 社交证明清单 / 转化话术

**验证**：`python3 scripts/marketing_claims_check.py --json`、`python3 scripts/release_audit.py --scope workspace --root .`、`python3 -m pytest tests/test_marketing_claims_check.py -v` 全过。

### Day 2 — **CI 硬门禁 + macOS 矩阵**

- [ ] `.github/workflows/ci.yml` macOS 矩阵扩到 14/15/26
- [ ] `app` job 加 `python3 scripts/release_preflight.py --with-dmg-smoke`（opt-in marker `NETFIX_RUN_DMG_SMOKE=1`）
- [ ] `release-gate` job：`python3 scripts/release_audit.py --scope workspace --root .`
- [ ] 仓库 Settings → Branch protection → required check `ci / pytest`

### Day 3 — **MCP 安全 + 日志脱敏**

- [ ] `netfix/mcp_server.py:netfix_fix_issue` 对齐 `SYSTEM_FIX_CONFIRMATION`（参考 `api.py:_execute_confirmed_fix`）
- [ ] `netfix/mcp_server.py` 出口套 `_strip_internal_secrets`
- [ ] `netfix/agent_tools.py` 加 `_safe_stderr` helper，全量替换 `res["stderr"]` 路径
- [ ] `netfix/logs.py:append_event` 写盘前 `redact_report`
- [ ] 加测试 `tests/test_mcp_fix_confirmation.py` 验证 Tier 2 必须二次确认
- [ ] 加测试 `tests/test_logs_redaction.py` 验证事件脱敏

### Day 4 — **macOS 底层硬化**

- [ ] `netfix/keychain.py` dev 模式禁用 `-T`
- [ ] `netfix/safety.py` 词边界 + 补 `osascript` 黑名单
- [ ] `netfix/proxy_bridge.py:_BridgeServer` `address_family = AF_INET`
- [ ] `netfix/proxy_bridge.py:_tunnel` wall-clock 60s
- [ ] `netfix/residential_proxy.py:_run_networksetup` 累计结果
- [ ] `netfix/residential_proxy.py:write_journal` drop `auto_proxy_url`

### Day 5 — **Agent-native 创新：evidence 链 + list_fixes**

- [ ] `netfix/reasoner.py` root_cause 加 `evidence: [{diagnostic, status, weight}]`
- [ ] `netfix/mcp_server.py` 加 `netfix_list_fixes` 工具（基于 `symptoms.json` 读出）
- [ ] `netfix/mcp_server.py` `netfix_fix_issue.issue` 字段加 `oneOf` enum
- [ ] `rules/symptoms.json` 给每条 symptom 加可选 `evidence` 字段
- [ ] 加测试 `tests/test_reasoner_evidence.py` 验证 evidence 链正确

### Day 6 — **增长素材：截图 + GIF + Cases 引流**

- [ ] `assets/github/zh/` + `en/` 各加 6 张真实 App 截图（脱敏 demo profile）
- [ ] `assets/github/...` 加 1 个 8 秒内 `codex --json` 终端 GIF
- [ ] `assets/github/...` 加 1 个 8 秒内 in-app 还原网络 GIF
- [ ] README "Real cases 段" 加 `cases/2026-06-29-普通用户代理部署体验审查.md` 摘要 + 链接

### Day 7 — **发布日**

- [ ] `python3 -m pytest -q` + `release_audit` + `release_preflight --with-dmg-smoke` 全过
- [ ] `python3 scripts/source_export.py --zip --json` 出新 source 快照
- [ ] 打 GitHub Release tag `v0.2.0-qa.2`，附 README 引导截图
- [ ] 在 Hacker News 发 Show HN（问题陈述为主，不堆功能）
- [ ] 在 V2EX / NodeSeek / InfoQ CN 发中文版（用 cases 引流）
- [ ] 30 star 之后写 follow-up 推文，对比 before/after 真实诊断

---

## 9. 已落地的修补（本会话内直接修的部分）

| 文件 | 改动 |
|---|---|
| `.github/repository.yml` | topics 30 个，加 `claude` / `cursor` / `kimi` / `mcp` / `model-context-protocol` / `homebrew` / `apple-silicon` / `ipv6` / `network-monitor`；删 `network-triage` / `proxy-diagnostics` |
| `.github/PULL_REQUEST_TEMPLATE.md` | 加 Architecture / Affected Areas / Output Schema Impact / Linked Issues 四段 |
| `docs/github/RELEASE_NOTES_V0.2.0.md` | 重写为三段式：What changed / Try it / Known limits |
| `docs/github/STAR_GUIDE.md` | 加 4 列表对比 / 社交证明清单 / Cases 链接 / 转化话术 / 删 STAR 自检命令（移到 OPEN_SOURCE.md） |
| `README.md` | 顶部加 "它做什么 / 60 秒开始 / 跟现有工具比 / 它不做什么" 四段 + "Real cases 速览" 段 |
| `README.en.md` | 同步英文版四段首屏 + Cases 段 |

**测试验证**：
- `python3 scripts/marketing_claims_check.py --json` ✅
- `python3 scripts/release_audit.py --scope workspace --root .` ✅
- `python3 -m pytest tests/test_marketing_claims_check.py -v` ✅ 5 passed
- `python3 -m pytest -q` 整体：399 passed, 1 skipped（`test_marketing_claims_check` 单独 5 项全过，无 regression）

**未做（按上面 Day 2-7 排期）**：CI 矩阵 / MCP Tier 2 magic word / 日志脱敏 / macOS 底层硬化 / agent-native evidence 链 / 截图 GIF / 实际发布日运营。

---

## 10. 关键文件路径速查

- 入口：`netfix/netfix.py` / `netfix/cli.py:978 main()`
- 诊断：`netfix/detect.py` / `netfix/diagnose.py` / `netfix/reasoner.py` / `netfix/explain.py`
- 修复：`netfix/fix_engine.py` / `netfix/safety.py`
- LLM：`netfix/llm_explain.py` / `netfix/llm_provider.py` / `netfix/llm_budget.py` / `netfix/deepseek_sidecar.py`
- 安全：`netfix/keychain.py` / `netfix/redaction.py` / `netfix/proxy_bridge.py` / `netfix/residential_proxy.py` / `netfix/proxy_monitor_service.py`
- MCP：`netfix/mcp_server.py` / `netfix/agent_tools.py` / `netfix/api.py`
- 规则：`rules/symptoms.json` / `rules/services.json` / `netfix/cores/`
- 发布：`scripts/source_export.py` / `scripts/release_export.py` / `scripts/release_audit.py` / `scripts/release_preflight.py` / `scripts/release_gate.sh` / `scripts/verify_dmg_backend.sh` / `scripts/marketing_claims_check.py` / `scripts/path_sanitizer.py`
- 增长：`.github/repository.yml` / `.github/ISSUE_TEMPLATE/*` / `.github/PULL_REQUEST_TEMPLATE.md` / `docs/github/STAR_GUIDE.md` / `docs/github/SCREENSHOTS.md` / `docs/github/RELEASE_NOTES_V0.2.0.md` / `assets/github/`
- CI：`.github/workflows/ci.yml` / `Makefile` / `pyproject.toml`

---

## 11. 一句话结论

**Netfix 的工程已经比 90% 同类开源项目扎实，但 GitHub 端首屏看上去只比"个人脚本"强一档。**

把上面 6.1 的 10 条"必须改"做掉 8 条，陌生用户 5 秒测试就从"失败"升到"过关"，Star 漏斗会立刻松动；
把 6.2 的 12 条"应该改"做掉一半，可信度会从"个人项目"升到"可以给同事用"；
Day 7 那一发 Show HN + 三条中文社区 + 一组真实截图 + 3 个 GIF，是把 30 星推到 300 星的临界点。

**别再写 10000 字的 PRODUCT_STRATEGY_V3 了。** 7 天写代码 + 截图，胜过 70 天写 PPT。
