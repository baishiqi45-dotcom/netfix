# AGENTS.md — netfix Agent 工作手册

> 适用范围：Kimi、Minimax、Codex 等需要帮用户排查 macOS 网络问题的 Agent。

---

## 核心原则

**遇到任何网络问题，先跑 netfix，再读 JSON。**

不要一上来就手拼 `ping`、`curl`、`scutil` 命令。netfix 已经把这些检查封装好，并且按统一格式输出，LLM 直接消费即可。

---

## 标准入口

```bash
python3 netfix.py codex --json
```

这条命令会同时检查：

- 当前系统代理设置
- 运行中的代理核心（xray / sing-box / mihomo / Clash 等）
- Codex / OpenAI / GitHub 直连与走代理的可达性
- 本地规则引擎给出的根因和修复建议

如果问题明显是 DNS、Wi-Fi、SSL 或连通性，也可以分项跑：

```bash
python3 netfix.py dns example.com --json
python3 netfix.py wifi --json
python3 netfix.py ssl github.com --json
python3 netfix.py connectivity 8.8.8.8:443 --json
```

---

## 怎么读 JSON 输出

重点关注这几个字段：

| 字段 | 含义 | 用法 |
|------|------|------|
| `environment.active_profile` | 当前代理节点 | 判断是不是当前节点挂了 |
| `environment.profiles` | 所有可用节点 | 给用户推荐切哪个 |
| `diagnostics` | 每个探针的实测结果 | 看哪一层失败 |
| `root_causes` | 本地规则推断的根因 | 按置信度排序 |
| `fixes` | 自动/半自动修复 | 按 Tier 执行 |
| `manual_steps` | 必须手动的步骤 | GUI 操作、路由器后台等 |

---

## 修复执行规则

`fixes` 数组里每一项都有 `tier`，你可以把它理解成“风险等级”：

- **Tier 1 / 可自动执行**：低风险，例如刷新 DNS 缓存。可以直接执行。
  ```bash
  python3 netfix.py fix --issue flush-dns-cache
  ```
- **Tier 2 / 需用户确认**：会改系统配置，**必须先问用户**，不能因 `--yes` 绕过。只有规则明确标记 `transactional_rollback=true` 时才可执行；当前通用 Tier 2 规则没有可验证快照，只允许 dry-run，真实变更使用代理专用确认端点或交给用户手动处理。
  ```bash
  python3 netfix.py fix --issue reset-system-proxy --dry-run
  # 给用户看 diff，确认后再去掉 --dry-run
  ```
- **Tier 3 / 只能手动**：只给手动步骤清单，不执行任何命令。把 `manual_steps` 逐条念给用户。

**注意**：`--yes` 只对 Tier 1 生效。Tier 2 无论有没有 `--yes`，都要用户亲口确认。

---

## 不要自己拼诊断命令

netfix 没覆盖的场景才手写命令。优先顺序：

1. `python3 netfix.py codex --json`（快速检查）
2. `python3 netfix.py triage --json` 或分项诊断（别名：`python3 netfix.py check --json`）
3. `python3 netfix.py doctor --json`（完整体检；别名：`python3 netfix.py full-check --json`）
4. `python3 netfix.py kb --query <关键词>` 查 runbook（别名：`python3 netfix.py guide --query <关键词>`）
5. 最后才查 `final.md` 或手写命令

---

## 修好后做什么

用户确认问题解决后，主动提议：

> 要不要把这次 case 记到 `cases/` 里？下次同样症状可以直接匹配。

如果用户同意，按这个格式落盘：

```markdown
# YYYY-MM-DD - 一句话症状

- 触发场景：...
- netfix 关键输出：...
- 根因：...
- 实际修复：...
- 验证：...
```

文件名：`cases/YYYY-MM-DD-关键词.md`

---

## 禁止

- ❌ 不问用户就执行 Tier 2 修复
- ❌ 绕过 netfix 自己拼一堆诊断命令
- ❌ 把 `final.md` 全文 dump 给用户
- ❌ 输出“在当今”“综上所述”“希望对你有帮助”等 AI 腔
- ❌ 用户说“好了”之后继续深挖

---

## P0 App 发布与文档契约

根目录 README 只面向 App 用户，首段只说明：粘贴用户已有的 HTTP/SOCKS 参数 → 先验证 → 用户确认后安全启用 → 随时停止并恢复。不要在 README 承诺“一键诊断”或“重启即可恢复”，也不要把 CLI、HTTP API、MCP 命令重新放回 README；这些接口统一维护在 `docs/developer/interfaces.md`。

macOS 候选构建必须满足：

- `gui/macos/build_app.sh` 自动使用仓库或本机已经存在的 PyInstaller 构建独立 `netfix-backend`，不安装插件或构建依赖。
- `Netfix.app/Contents/MacOS/netfix-backend` 必须存在且可执行；运行时优先启动这个 bundle 内 backend，候选 App 不依赖系统 Python。
- `pyproject.toml` 是唯一版本来源，脚本和产物名不得另写硬编码版本。
- `release-manifest.json` 必须写入 `git_sha`、`dirty`、`source_fingerprint`、`backend_sha256`、`app_executable_sha256`、`build_id`、`built_at`、`version`。
- backend 或 App 主可执行文件缺失、不可执行、SHA-256 不符时，构建和 DMG 校验必须失败。
- 当前 P0 产物只能标为**未签名、未公证候选**：没有 Developer ID 签名，也没有 Apple 公证。backend 的 ad-hoc 本地签名不等于发行签名。
- 构建脚本不得退出、启动或安装 App，也不得创建或修改桌面链接。

发布构建入口：

```bash
gui/macos/build_app.sh --release-candidate
python3 scripts/release_manifest.py verify \
  --app-bundle gui/macos/.build/Netfix.app \
  --manifest gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json \
  --repo-root .
```

---

## HTTP API 与 MCP 服务

netfix 也提供两种机器可消费的接口：

```bash
# 本地 HTTP API（127.0.0.1，默认自动分配端口）
python3 netfix.py server --host 127.0.0.1 --port 0

# MCP stdio 服务器（JSON-RPC，用于 Kimi / Codex / Claude / Cursor 等 MCP 宿主）
python3 -m netfix.mcp_server
```

HTTP 端点：

- `GET /health`
- `GET /capabilities`
- `POST /run`  `{ "command": ["codex"], "timeout": 30, "async": false }`
- `GET /jobs/<id>`
- `GET /report/latest`
- `GET /services/groups`
- `GET /dashboard/state`
- `GET /llm/providers`
- `POST /settings/llm`
- `POST /explain_llm`

MCP 暴露的工具包括 `netfix_codex`、`netfix_services`、`netfix_triage`、`netfix_doctor`、`netfix_report`、`netfix_kb_query`、`netfix_fix_issue`、`netfix_rollback`、`netfix_proxy_switch`、`netfix_chat`、`netfix_symptom_intake`。`netfix_rollback` 也会改系统状态，必须传 `confirmed=true` 和 `confirmation=APPLY_SYSTEM_FIX`；`POST /run` 不接受 `rollback`。

对话式排查动线：用户用自然语言描述症状时，先调 `netfix_symptom_intake` 匹配规则库并拿到建议工具，执行建议工具收集证据，再用 `netfix_chat` 带着 `history`（最近 20 条 user/assistant 消息）做多轮解释。

Agent 优先用这些更清楚的新工具：

- `netfix_list_fixes`：列出当前已知修复项、Tier、风险和是否需要确认。
- `netfix_dry_run_fix`：只预演一个修复，不改系统设置。
- `netfix_apply_fix`：执行可安全回滚的修复。Tier 2 除了必须传 `confirmed=true` 和 `confirmation=<见下表>`，规则还必须具备已验证的事务快照；否则返回 `transactional_rollback_unavailable`。`magic_word` 是 `confirmation` 的 deprecated alias，优先用 `confirmation`。
- `netfix_evidence_chain`：给出“为什么判断这个根因”的诊断证据链。
- `netfix_sanitized_report`：返回已脱敏报告，适合贴 issue 或发给 AI。

#### Confirmation 字面值清单（按触发条件）

任意 `Tier ≥ 2` 操作必须传对应 magic phrase；HTTP/MCP/CLI 三处用法不一致时以代码为准：

| Confirmation 字面值 | 触发路径 | 风险等级 |
|---|---|---|
| `APPLY_SYSTEM_FIX` | `POST /fixes/execute`, `netfix_apply_fix` | Tier 2：恢复系统网络 |
| `TEST_LLM_PROVIDER` | `POST /llm/test` | Tier 1：触发一次 LLM 测试调用 |
| `TEST_LLM_CHAIN` | `POST /llm/chain-test` | Tier 1：触发 LLM 链路测试 |
| `APPLY_PROXY_PROFILE` | `POST /proxy/<id>/apply` | Tier 2：把代理写进系统网络 |
| `ROLLBACK_PROXY_PROFILE` | `POST /proxy/profiles/rollback` | Tier 2：回滚上次代理部署 |
| `RESTORE_STALE_PROXY_BRIDGE` | `POST /proxy/bridge/recover` | Tier 2：从 stale 状态恢复 |
| `RESTART_STALE_PROXY_BRIDGE` | `_record_startup_bridge_check` → `restart_stale_bridge` | Tier 2：重启桥接 |
| `IMPORT_DEEPSEEK_SIDECAR_KEY` | `POST /llm/import-deepseek-sidecar-key` | Tier 1：写入 Keychain |
| `DELETE_NETFIX_LOCAL_DATA` | `POST /data/clear` | Tier 2：清空本地数据 |

新增 confirmation 字面值时必须同步：① `netfix/api.py` / `residential_proxy.py` / `deepseek_sidecar.py` 的常量；② 本表；③ `tests/test_docs_contract.py` 的字面值断言。

旧的 `netfix_fix_issue` 仍保留兼容，但新 Agent 应该优先 `list_fixes → dry_run_fix → apply_fix`。

### 在 Kimi Code CLI 中注册

```bash
./scripts/install_mcp.sh --kimi
```

### 在 OpenAI Codex CLI 中注册

```bash
./scripts/install_mcp.sh --codex
```

远程源码注册、App 候选安装和发布预检分别由以下脚本维护；这些属于开发者/Agent 入口，不回填根 README：

- `scripts/install_codex_mcp_from_github.sh`
- `scripts/install_mac_app_from_github.sh`
- `scripts/release_preflight.py`

也可以预览将要执行的注册命令，不写入任何 Agent 配置：

```bash
./scripts/install_mcp.sh --all --dry-run
```

### 在 Minimax（Function Calling）中使用

Minimax 没有官方 MCP client，但模型支持 Function Calling。把 `netfix/mcp_server.py` 的 `tools/list` 输出转成 OpenAI-compatible functions，让模型在需要时调用本地 HTTP API：

```bash
# NETFIX_API_TOKEN 可从 App 或 ~/.netfix/api-token-<pid>.txt 获取
curl -s http://127.0.0.1:8765/run \
  -H "X-Netfix-Token: $NETFIX_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":["codex"],"timeout":15}'
```

---

## 快速参考

```bash
# 一键看 Codex 健康
python3 netfix.py codex --json

# 自然语言问网络问题（用户口语主诉的统一入口）
python3 netfix.py ask "我网速很慢"

# 执行 Tier 1 修复（dry-run 先看）
python3 netfix.py fix --issue flush-dns-cache --dry-run
python3 netfix.py fix --issue flush-dns-cache

# 回滚上一次 Tier 2 变更
python3 netfix.py rollback

# 查知识库
python3 netfix.py kb --query MTU
```
