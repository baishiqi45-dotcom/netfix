# Netfix 产品力与架构升级报告（2026-06）

> 本文档由 agent team 对 `/Users/qibaishi/Desktop/网络/` 进行对抗性产品与工程审计后整理。
> 目标：回答“为什么产品看起来会卡住、修不好、不好用”，并给出从“止血”到“LLM Agent”的演进路线。

---

## 1. 执行摘要

### 1.1 当前状态

Netfix 已经具备了一个网络自救工具所需的**基础骨架**：本地 Python 诊断引擎、规则化根因推理、SwiftUI 菜单栏面板、修复与回滚、MCP 工具暴露、事件时间线。但从真实用户视角看，它目前更像是一个**“能跑 demo 的开发者工具”**，而不是一个**“网络不通时用户愿意依赖的产品”**。

### 1.2 用户视角最痛的 5 个问题

| # | 痛点 | 典型表现 | 根因一句话 |
|---|---|---|---|
| 1 | **设置打不开 / 卡住** | 点“设置”无响应 | SwiftUI `Settings` 场景在菜单栏+popover 形态下 responder-chain 不可靠；自定义窗口也受后端状态影响 |
| 2 | **一键修复修不好** | 检测出 IPv6、DNS、代理等问题，点修复后仍是“修复完成”，问题还在 | `fix --all` 只跑 Tier 1；大量症状（IPv6 泄漏、代理认证、SSL 证书、Wi-Fi 问题）没有 `fixes`，只有 `manual_steps` |
| 3 | **管理员权限修复挂死** | 点“关闭 IPv6”后弹 command timed out | `sudo`/`networksetup` 在 GUI 子进程里等 TTY 密码；虽有 osascript 兜底，但超时链路与错误反馈仍然很差 |
| 4 | **状态灯看不见 / 看不懂** | 菜单栏图标在 Retina 屏上过小；未知状态显示黄色让用户误以为网络异常 | 图标合成逻辑未适配高分屏与红绿色盲；状态文案技术化 |
| 5 | **错误信息不解决问题** | “command timed out”“The request timed out”“后端进程异常退出” | 错误未经产品化翻译，缺少“重试/复制命令/查看日志/手动步骤”等下一步 |

### 1.3 核心结论

1. **先止血，再谈 AI。** 在 LLM 接入之前，必须让“诊断→修复→反馈”这一主链路真正闭环。否则 LLM 只会更快地生成让用户失望的建议。
2. **修复≠执行命令。** 当前把“检测出问题→执行命令”当成修复，但大量网络问题（代理客户端配置、节点失效、证书、Wi-Fi 信号）无法也不应该由本地命令自动解决。产品需要区分“自动修复”“引导用户手动修复”“仅解释”。
3. **LLM 应该作为解释层与规划层，而不是执行层。** 网络探测、权限命令、备份回滚必须保留本地确定性逻辑；LLM 负责把报告讲成人话、在规则未覆盖时做二次推理、生成针对用户代理客户端的精确手动步骤。
4. **云端国产 LLM API key 模式，本地规则兜底。** 不默认使用本地模型（本地跑大模型对普通用户过于笨重、速度慢、占用存储）。由用户在 Settings 中填入自己的国内模型 API key；文本解释默认优先 DeepSeek，Kimi/Moonshot、MiniMax、Qwen 作为国内备用链路。图片问诊不能走 DeepSeek，只能走已验证支持 `image_url` 的国内多模态候选（当前产品链路为 MiniMax -> Kimi -> Qwen）。上传前对报告做脱敏（移除/哈希出口 IP、节点地址、token 等敏感字段）；云端不可达、用户未配置 key 或用户关闭云端 AI 时，回退到现有 `explain.py` 规则模板。

---

## 2. 用户旅程对抗性审计

### 2.1 启动阶段：信任在 5 秒内建立或崩塌

| 问题 | 严重度 | 位置 | 现象 | 根因 |
|---|---|---|---|---|
| App Bundle 缺少后端脚本时直接崩溃 | P0 | `Backend.swift:24` | 双击 App 直接退出 | `fatalError` 而不是降级到失败状态 |
| 硬编码 `/usr/bin/python3` | P1 | `Backend.swift:62` | 用户系统 Python 路径不同则启动失败 | 未探测 `which python3` 或 Bundle 内 Python |
| 后端端口解析无超时 | P1 | `Backend.swift:130-146` | 界面永久“正在启动引擎…” | 依赖 stdout 正则，无启动 deadline |
| 后端异常退出后 UI 仍显示“就绪” | P1 | `Backend.swift:91-101` | 按钮可点但所有 API 失败 | `terminationHandler` 仅在 `.starting/.failed` 时更新状态 |
| 首次引导“稍后设置”直接完成 | P1 | `WelcomeView.swift:37-39` | 用户跳过权限，后续诊断大量失败 | 没有区分“跳过本次”和“我明确不需要” |
| 权限页不验证是否真正授权 | P1 | `OnboardingView.swift:50-51` | 用户没点系统设置里的允许也能进入下一步 | 未查询本地网络授权状态 |

**产品原则：** 启动失败时，必须让用户知道“发生了什么”和“能做什么”（重启、检查安装、重新授权），而不是崩溃或假死。

### 2.2 Dashboard：信息密度高，但可操作性低

| 问题 | 严重度 | 位置 | 现象 | 根因 |
|---|---|---|---|---|
| 进度条是“假进度” | P1 | `DashboardViewModel.swift:592-620` | 诊断实际 30s，进度条按固定 1.5s 推进 | 未基于后端真实事件 |
| 一键修复可能什么都不修 | P0 | `cli.py:445-468` | 点完显示“修复完成”，问题仍在 | `--all` 只跑 Tier 1；大量症状无自动 fix |
| 修复失败显示“修复完成” | P1 | `DashboardViewModel.swift:519-536` | 只看报告是否返回，不区分修复成功个数 | `overallStatus == .ok` 即显示“修复完成” |
| 错误 Banner 无下一步 | P1 | `DashboardView.swift:512-515` | 只看到 command timed out | 缺少重试/复制/查看日志/手动步骤 |
| 状态灯/颜色含义不清 | P2 | `StatusIconView.swift` + `AppDelegate.swift:149-164` | 未知状态黄色让用户误以为异常；红绿色盲不友好 | 无文字标签，颜色是主要信息 |
| 六张固定卡片与实际诊断错位 | P1 | `DashboardView.swift:132-139` | 卡片显示“未检测”，详细列表里有问题 | `layer` 字段缺失或不匹配固定卡片 |

**产品原则：** 仪表盘应该回答三个问题：
1. 我现在能不能上网？
2. 如果不能，最可能的原因是什么？
3. 我能做什么？（自动修复 / 手动步骤 / 问 AI）

当前 UI 把“检测到 N 个问题”当成核心信息，但用户真正需要的是“下一步动作”。

### 2.3 修复流程：自动与手动的边界模糊

| 问题 | 严重度 | 位置 | 现象 | 根因 |
|---|---|---|---|---|
| 撤销结果可能撒谎 | P0 | `fix_engine.py:298-300` | 显示“已撤销”，实际配置没恢复 | `ok` 逻辑基于字典非空，而非每个备份是否成功恢复 |
| Tier 2 修复自动绕过确认 | P0 | `cli.py:474-491` | `--yes` 让 Tier 2 也直接执行 | `auto_confirm` 未限定 Tier |
| 自动修复仍会弹系统密码框 | P1 | `fix_engine.py:210-216` | 开启“自动修复”后深夜突然弹框 | Tier 1 里含 `sudo` 的 fix 仍走 osascript 授权 |
| 验证失败不影响修复结果 | P1 | `fix_engine.py:226-236` | 修复后验证不通过，仍显示 ok | `verify`/`verify_diagnostic` 失败未置 `ok=false` |
| shell 复合命令无法执行 | P1 | `fix_engine.py:206-217` | rules 里 `&&`、管道、重定向失效 | `shlex.split` + `shell=False` |
| 修复失败后 `--report` 掩盖错误 | P1 | `cli.py:480-485` | 返回新报告，看不到 fix 失败详情 | `--report` 分支直接重新诊断 |

**产品原则：**
- Tier 1 = 用户无感、不弹框、可自动。
- Tier 2 = 必须明确确认（UI 弹窗或系统密码框），执行前备份。
- Tier 3 = 只给手动步骤，不执行命令。
- 任何修复失败，必须让用户知道“哪一步失败了”“为什么”“下一步是什么”。

### 2.4 设置窗口：开关不少，反馈不足

| 问题 | 严重度 | 位置 | 现象 | 根因 |
|---|---|---|---|---|
| 登录项失败无提示 | P0 | `SettingsView.swift:242-255` | Toggle 被默默拨回 | catch 里只回退状态 |
| 服务 Tab 硬编码开发路径 | P1 | `SettingsView.swift:225` | 其他 Mac 上服务列表加载失败 | 回退路径 `/Users/qibaishi/Desktop/网络/...` |
| 通知 Toggle 不同步真实授权 | P1 | `SettingsView.swift:55-60` | 系统拒绝后 UI 仍显示开启 | 未在 onChange 后读取授权结果 |
| 图标样式切换不生效 | P1 | `SettingsView.swift:64-67` + `AppDelegate.swift` | 切换后菜单栏图标不变 | `updateStatusIcon` 未读取 `iconStyle`（已部分修复） |
| 服务分组开关是死开关 | P1 | `SettingsView.swift:81-113` | 用户点了无效 | 使用 `.constant(true)` |

---

## 3. 工程健壮性与卡住根因

### 3.1 后端进程：生命周期管理是整个产品的底座

- **崩溃点：** `Backend.backendPath` 找不到 `netfix.py` 时 `fatalError`。
- **假死点：** 端口解析依赖 stdout 正则，无启动超时；健康检查过于敏感，一次失败即置 `.failed`。
- **并发风险：** `outputBuffer`/`errorBuffer` 在 `readabilityHandler` 后台队列与主线程之间无锁读写。
- **重启风险：** `restart()` 等 0.5s 后启动，原进程可能未释放端口。

**建议：** 把后端启动改成“状态机 + deadline + 指数退避重试”：
- 启动阶段：尝试 3 次，每次 15s 内未就绪则失败。
- 运行阶段：健康检查失败时先进入 `degraded`，连续 3 次失败才 `failed`。
- 停止阶段：先 `terminate()`，再 `waitUntilExit()`，再启动新进程。

### 3.2 超时链路：层层叠加，用户等待不可预期

```
Swift UI: timeout + 30s
    -> URLSession timeoutInterval
        -> API /run timeout
            -> run_cli subprocess timeout
                -> doctor 每项诊断 timeout = min(10, total_timeout)
```

结果是：用户点击“一键诊断”可能等 150s，最后只看到 `command timed out`，中间没有任何进度。

**建议：**
- `/run` 默认走异步 job，前端轮询 `/jobs/<id>`，UI 实时显示步骤。
- 诊断并行化（同层并发），并通过 SSE/轮询返回实时进度。
- Swift 端 timeout 与后端 command timeout 保持一致，不再额外 +30s。

### 3.3 授权与权限：sudo 不能 silently happen

- `sudo`/`networksetup` 在 GUI 子进程里没有 TTY，会挂起。
- 当前用 `osascript 'do shell script ... with administrator privileges'` 兜底，但：
  - 多个 sudo 命令会连续弹多次密码框。
  - 无人值守的 HTTP/MCP 调用会超时。
  - 用户取消后错误信息不够明确。

**长期方案：** 使用 `SMJobBless` 安装一个受信任的 root helper（`netfix-helper`），Tier 1 自动修复通过 helper 静默执行一次授权；Tier 2+ 仍弹系统密码框。
**短期方案：** 在 HTTP/MCP 路径上，Tier 2+ 返回 `pending_approval` 状态，让 UI 显式弹窗确认后再执行。

### 3.4 测试覆盖：关键路径几乎裸奔

| 模块 | 当前测试 | 缺失 |
|---|---|---|
| Swift UI | 3 个 JSON 解码测试 | Backend 启动/重启/端口解析、DashboardViewModel 状态流、Settings 登录项失败 |
| FixEngine | dry-run、backup、rollback | sudo/osascript 授权失败、shell 复合命令、verify 失败、并发 |
| API | health、capabilities、sync/async run | 超时链、并发耗尽、重复 `--timeout`、大请求体 |
| Reasoner | 无 | 规则改动回归、边界 case |
| E2E | 无 | 构建 .app 后启动并点击诊断 |

---

## 4. LLM Agent 架构方案

### 4.1 当前代码中已有的 LLM/Agent 资产

- `agent_tools.py`：20+ 只读/可写工具函数。
- `mcp_server.py`：把这些工具暴露为 MCP server。
- `explain.py`：规则化报告解释。
- `reasoner.py`：规则化根因推理。
- `kb.py` + `final.md`：知识库。

### 4.2 适合交给 LLM 的部分

| 能力 | 当前实现 | LLM 化价值 |
|---|---|---|
| 报告解释 | 硬编码模板 | 更自然、上下文感知的解释；可区分小白/进阶模式 |
| 根因排序与未知模式 | 规则匹配 | 规则未覆盖时做二次推理 |
| 修复建议生成 | 固定 manual_steps | 根据用户具体代理客户端（v2rayN/Clash/Surge）生成精确点击路径 |
| 用户自然语言问诊 | 无 | “我 ChatGPT 打不开”→自动调用工具链 |
| 案例沉淀 | 手动 markdown | 自动总结并生成 case |

### 4.3 必须保留本地确定性的部分

- 网络探测（ping/dig/curl/socket/scutil）
- 系统状态读取（ifconfig/route/networksetup）
- 权限/提权命令（sudo/osascript/SMJobBless）
- 安全分级（Tier 0-3）
- 修复执行、备份、journal、回滚

### 4.4 技术选项对比

| 维度 | DeepSeek API | MiniMax API | Moonshot Kimi API | 阿里通义 Qwen API | OpenAI/Anthropic API |
|---|---|---|---|---|---|
| 产品角色 | **文本解释默认首选** | 图片问诊优先候选 | 图片问诊备用候选 | 文本/图片备用候选 | 全球可选兜底 |
| 当前预设 | DeepSeek 文本模型 | MiniMax-M3 | Kimi/Moonshot | qwen-plus / qwen-vl-plus | OpenAI-compatible |
| 模型质量 | 高（中文推理强） | 高（多模态与工具链适配） | 高（长上下文优秀） | 高（中文网络场景适配好） | 最高 |
| 成本 | **低成本、大吞吐，适合作为默认文本链路** | 中 | 中 | 中 | 高 |
| 图片/截图问诊 | 不作为视觉供应商使用 | 支持后可作为优先链路 | 支持后作为备用链路 | qwen-vl 系列作为备用链路 | 支持但不做国内默认 |
| 隐私/合规 | 国内供应商 | 国内供应商 | 国内供应商 | 国内供应商 | 可能涉及数据出境 |
| 延迟（国内） | 低-中 | 低-中 | 低-中 | 低 | 中-高（受国际链路影响） |
| API 兼容性 | OpenAI-compatible | OpenAI-compatible | OpenAI-compatible | OpenAI-compatible / 兼容模式 | 原生 / OpenAI-compatible |
| 离线可用 | 否 | 否 | 否 | 否 | 否 |
| 推荐用法 | **默认文本** | **图片问诊优先** | 图片问诊备用、长上下文 | 文本/图片备用 | 不推荐默认 |

**不推荐本地模型：** 本地 Ollama/MLX 需要下载数 GB 模型、占用内存与 GPU、首次启动慢，对普通 macOS 用户过于笨重；且当用户网络出问题时，本地模型并不能解决“需要外部知识”的问题。

**推荐组合：**
- **文本默认：** 国产云端模型优先 DeepSeek，定位是低成本、大吞吐的中文网络故障解释主力。
- **图片问诊：** DeepSeek 不承担图片/截图问题；用户启用实验入口并确认上传后，按 MiniMax -> Kimi -> Qwen 选择已配置 API Key 的国内多模态供应商。
- **配置方式：** 用户在 Settings 中填入自己的 API key；App 通过标准 OpenAI-compatible 协议调用，每个 provider 使用独立 Keychain account，避免拿 DeepSeek 的 key 去调用 MiniMax/Kimi/Qwen。
- **脱敏：** 上传前移除/哈希出口 IP、代理节点地址、认证 token、MAC 地址等敏感字段；只保留诊断状态、错误类型、网络层抽象信息。
- **fallback：** 云端不可达、用户未配置 key 或用户主动关闭时，回退到 `explain.py` 规则模板。

### 4.5 最小可行集成架构（MVP）

```
┌─────────────────────────────────────────────┐
│  SwiftUI Dashboard / Settings               │
│  [新增] “问 AI” 按钮 / 设置项                │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  Python Backend HTTP API                     │
│  /run /report/latest /events /environment   │
│  [新增] POST /explain_llm                    │
│    输入：脱敏报告 JSON + 用户问题             │
│    输出：headline / explanation / actions   │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  LLM Router (netfix/llm_router.py)           │
│  1. 默认使用用户配置的国产云端 API key        │
│     （DeepSeek / Kimi / Qwen，OpenAI-compatible）│
│  2. 上传前对报告做脱敏处理                    │
│  3. 失败/无 key / 超时时 fallback 到 explain.py│
└─────────────────────────────────────────────┘
```

MVP 改动清单：
1. 新增 `netfix/llm_router.py`：prompt 模板、模型调用、失败 fallback；支持 OpenAI-compatible 端点。
2. 新增 `POST /explain_llm`：接收脱敏报告 + 用户问题，返回 LLM 生成的解释与建议。
3. `DashboardView.swift` 增加“问 AI”卡片；未配置 key 时引导用户去设置。
4. `SettingsView.swift` 增加：模型供应商选择、API key 输入（存储在 Keychain）、是否启用云端、隐私提示。“}

### 4.6 长期 Agent 架构

```
用户 / MCP Host
    │
    ▼
Intent Parser（LLM/规则混合）
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
Perception     Planner         Memory
agent_tools    LLM + Safety    对话/状态/case RAG
+ diagnose     Policy
    │              │
    └──────────────┘
                   ▼
          Action Executor
          Tier 0/1 自动执行
          Tier 2+ 弹窗确认
                   ▼
          Verification + Explanation Gen
```

关键设计：
- **Safety Policy 在中间层：** LLM 建议的动作先经过 `safety.classify_command` 和 Tier 校验。
- **记忆层：** SQLite 保存会话、报告摘要、用户偏好、成功/失败修复方案。
- **RAG：** `final.md`、`cases/`、成功修复记录向量化，LLM 检索相似 case。
- **可解释性：** 每个动作必须附带“用了什么工具、看到什么数据、为什么推荐”。

---

## 5. 分阶段路线图

### Phase 1：止血（1-2 周）——让用户能点、能修、能信

1. **Backend 启动兜底**
   - `Backend.swift:24` `fatalError` → `state = .failed("未找到后端脚本，请重新安装")`。
   - 探测 Python 解释器：`which python3` / Bundle 内 python，不要硬编码 `/usr/bin/python3`。
   - 增加 15s 启动 deadline；健康检查连续失败 3 次才置 `failed`。
2. **修复按钮真实反馈**
   - `fix --all` 无自动 fix 可跑时，返回 `no_auto_fixes: true`，Dashboard 显示“当前问题需手动处理”。
   - 修复失败时不再显示“修复完成”，而是显示具体失败步骤 + 手动步骤。
3. **撤销状态修复**
   - `fix_engine.py:298-300` 改为检查每个备份是否成功恢复。
4. **错误 Banner 产品化**
   - `command timed out` → “检测耗时过长，可能是网络质量差或代理无响应。”
   - 增加“重试 / 复制报告 / 查看日志”按钮。
5. **设置窗口反馈**
   - 登录项失败显示 Alert。
   - 通知 Toggle 同步真实授权状态。
   - 移除服务 Tab 硬编码路径。

### Phase 2：产品力（3-4 周）——让诊断→修复→反馈闭环

6. **真实进度与取消**
   - `/run` 默认异步 job + 前端轮询。
   - 诊断并行化，实时返回步骤。
   - 增加取消按钮，真正中断子进程。
7. **修复成功率提升**
   - 扩展 `rules/symptoms.json`，把常见症状映射到具体 fix。
   - 区分“自动修复”“需确认修复”“仅手动步骤”。
   - 修复执行记录保留在报告中，不被 `--report` 掩盖。
8. **Onboarding 闭环**
   - 权限页检查真实授权状态。
   - “稍后设置”后顶部常驻提示权限未开启。
9. **测试补全**
   - Swift：Backend 启动/重启、DashboardViewModel 状态流。
   - Python：sudo/osascript、超时链、并发诊断、reasoner 回归。

### Phase 3：LLM Agent（2-3 个月）——从工具到 agent

10. **LLM 解释 MVP**
    - `llm_router.py` + `POST /explain_llm`。
    - Dashboard “问 AI”入口。
    - 默认国产云端模型（DeepSeek / Kimi / Qwen），用户自填 API key；本地规则兜底。
11. **Agent Loop**
    - 接收自然语言目标 → 工具调用 → LLM 推理 → 建议动作 → 用户确认 → 执行 → 验证 → replan。
12. **记忆与 RAG**
    - SQLite 保存会话与修复历史。
    - cases/ 与 final.md 向量化检索。
13. **架构升级**
    - Swift ↔ Python 通信考虑迁移到 XPC/Unix Domain Socket，避免端口占用和防火墙弹窗。
    - 引入持久化状态机与审计日志。
    - 不采用本地端侧大模型（用户设备负担过重），保持“国产云端 API key + 本地规则兜底”模式。

---

## 6. 关键产品决策

### 6.1 产品定位

**Netfix 不应该定位成“一键修好所有网络问题的万能工具”**，因为：
- 大量网络问题（节点失效、账号被封、Wi-Fi 信号差、证书错误）无法通过本地命令自动修复。
- 用户真正需要的是：**“快速知道问题在哪、能不能自己修、不能自己修时下一步找谁/怎么做”**。

**建议定位：**
> **“你的本地网络急诊助手”** —— 典型 30-60 秒给出可信诊断，自动处理安全的基础问题，对需要手动处理的问题给出精确步骤；网络可用时通过国产云端 LLM 解释，网络不可用或未配置 key 时回退到本地规则模板。

### 6.2 自动修复的边界

| 问题类型 | 能否自动修 | 产品表现 |
|---|---|---|
| DNS 缓存污染 | ✅ Tier 1 | 自动刷新，不弹框 |
| 系统代理未生效 | ⚠️ Tier 2 | 弹系统密码框或让用户在代理客户端操作 |
| IPv6 泄漏 | ⚠️ Tier 2 | 弹系统密码框关闭 IPv6，或给出手动步骤 |
| 代理节点失效 | ❌ 手动 | 引导用户在代理客户端切换节点 |
| Wi-Fi 信号差 | ❌ 手动 | 给出“靠近路由器/重启路由器”步骤 |
| SSL 证书错误 | ❌ 手动 | 给出 openssl 检查步骤或联系管理员 |

### 6.3 LLM 边界

- **LLM 不能执行系统命令。** 只能建议 fix id，由本地 `FixEngine` 执行。
- **LLM 不能决定 Tier 2+ 是否执行。** 必须经过用户确认。
- **默认国产云端 API key 模式。** 不默认使用本地模型（笨重）；未配置 key 或云端不可达时回退到本地规则模板。
- **所有 LLM 建议必须可解释。** 展示“基于哪些诊断数据得出该结论”。

---

## 7. 近期最该改的 3 件事（如果只能做三件）

1. **让后端启动/失败/恢复稳定可靠。** 没有这一步，所有 UI 都是空中楼阁。
2. **让“一键修复”诚实。** 修不了就告诉用户为什么，并给出精确手动步骤；不要显示“修复完成”。
3. **接入国产云端 LLM 解释层（DeepSeek / Kimi / Qwen）。** 这是产品差异化最大的方向，但必须在前面两条稳定之后做，否则 LLM 只会更快地让用户失望。

---

## 8. 参考与延伸阅读

- [DeepSeek API 文档（OpenAI-compatible）](https://api-docs.deepseek.com/)
- [Moonshot Kimi API 文档](https://platform.moonshot.cn/docs/intro)
- [阿里通义千问 API 文档](https://help.aliyun.com/zh/dashscope/)
- [MCP-Diag: Deterministic protocol-driven network diagnostics](https://arxiv.org/html/2601.22633v1)
- [Tool Calling vs MCP vs Function Calling](https://composio.dev/content/ai-agent-tool-calling-guide)

---

*报告生成时间：2026-06-19*  
*参与审计 agent：用户体验与产品流程、工程健壮性与卡住根因、LLM Agent 架构研究*
