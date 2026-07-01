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

`fixes` 数组里每一项都有 `tier`：

- **Tier 1**：低风险，可以直接执行。
  ```bash
  python3 netfix.py fix --issue flush-dns-cache
  ```
- **Tier 2**：会改配置，**必须先问用户**，不能因 `--yes` 绕过。
  ```bash
  python3 netfix.py fix --issue reset-system-proxy --dry-run
  # 给用户看 diff，确认后再去掉 --dry-run
  ```
- **Tier 3**：只给手动步骤清单，不执行任何命令。把 `manual_steps` 逐条念给用户。

**注意**：`--yes` 只对 Tier 1 生效。Tier 2 无论有没有 `--yes`，都要用户亲口确认。

---

## 不要自己拼诊断命令

netfix 没覆盖的场景才手写命令。优先顺序：

1. `python3 netfix.py codex --json`
2. `python3 netfix.py triage --json` 或分项诊断
3. `python3 netfix.py doctor --json`（完整体检）
4. `python3 netfix.py kb --query <关键词>` 查 runbook
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

MCP 暴露的工具包括 `netfix_codex`、`netfix_services`、`netfix_triage`、`netfix_doctor`、`netfix_report`、`netfix_kb_query`、`netfix_fix_issue`、`netfix_rollback`、`netfix_proxy_switch`。

### 在 Kimi Code CLI 中注册

```bash
./scripts/install_mcp.sh --kimi
```

### 在 OpenAI Codex CLI 中注册

```bash
./scripts/install_mcp.sh --codex
```

也可以预览将要执行的注册命令，不写入任何 Agent 配置：

```bash
./scripts/install_mcp.sh --all --dry-run
```

### 在 Minimax（Function Calling）中使用

Minimax 没有官方 MCP client，但模型支持 Function Calling。把 `netfix/mcp_server.py` 的 `tools/list` 输出转成 OpenAI-compatible functions，让模型在需要时调用本地 HTTP API：

```bash
curl -s http://127.0.0.1:8765/run \
  -H "Content-Type: application/json" \
  -d '{"command":["codex"],"timeout":15}'
```

---

## 快速参考

```bash
# 一键看 Codex 健康
python3 netfix.py codex --json

# 执行 Tier 1 修复（dry-run 先看）
python3 netfix.py fix --issue flush-dns-cache --dry-run
python3 netfix.py fix --issue flush-dns-cache

# 回滚上一次 Tier 2 变更
python3 netfix.py rollback

# 查知识库
python3 netfix.py kb --query MTU
```
