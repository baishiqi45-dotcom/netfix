# netfix 设计文档

> 目标：把 `/Users/qibaishi/Desktop/网络` 从“脚本 + runbook”升级为一个**本地可独立运行、国产/海外 LLM 都能调用、Codex 挂了也能自救**的网络修复 Agent/CLI。

---

## 1. 环境事实（已确认）

- **平台**：macOS（darwin），默认路由接口 `en0`，网关 `10.103.20.1`。
- **GUI 客户端**：`/Applications/v2rayN.app/Contents/MacOS/v2rayN`（名字是 v2rayN，但运行时同时拉起 `xray` + `sing-box`）。
- **代理核心**：
  - `xray` 监听 `*:10808`（mixed inbound）。
  - `sing-box` 负责 Tun 模式（`--disable-color`，配置为 `configPre.json`，启动后unlink）。
- **系统代理**：HTTP/HTTPS/SOCKS 全部指向 `127.0.0.1:10808`；同时开启了 `ProxyAutoConfigEnable` + `http://wpad/wpad.dat`。
- **当前活动节点**：`cc-http`（HTTP 出口，`direct.miyaip.online:8001`）。
- **节点库**：`guiConfigs/guiNDB.db` SQLite，当前 4 条 ProfileItem；当前节点由 `guiNConfig.json` 的 `IndexId` 指定。
- **无 REST API**：`127.0.0.1:9090` 无响应，因此**不能通过 API 自动切换节点**，只能读配置 + 给出手动/半自动切换方案。

---

## 2. 核心原则

1. **离线优先**：除真实网络探针外，不依赖外网 LLM、不依赖 pip 第三方包。
2. **LLM 可调用**：所有命令支持 `--json`，Kimi/Minimax/Codex 只需要会读 stdout 即可代为处理。
3. **安全分级**：只读 / 低风险自动 / 需确认 / 仅手动清单 四级。
4. **客户端无关**：先自动检测实际运行的核心（xray/sing-box/mihomo/clash/wireguard），再决定策略。
5. **复用现有资产**：`bin/*.sh` 与 `final.md` 不平反，逐步封装成模块。

---

## 3. 模块架构

```
netfix/
├── __main__.py          # python3 -m netfix 入口
├── cli.py               # argparse 子命令与 --json/--dry-run/--yes
├── constants.py         # 路径、端口、端点、版本
├── detect.py            # 平台/进程/端口/客户端自动检测
├── cores/
│   ├── base.py          # CoreBase 抽象类
│   ├── v2rayn.py        # v2rayN (xray+sing-box) 适配
│   ├── mihomo.py        # mihomo/Clash 适配（支持 External Controller API）
│   ├── singbox.py       # sing-box standalone 适配
│   ├── xray.py          # xray standalone 适配
│   └── wireguard.py     # WireGuard App/命令行适配
├── codex.py             # Codex/OpenAI/GitHub 可达性检查
├── diagnose.py          # 调度并执行诊断动作（脚本/Python）
├── reasoner.py          # 本地规则引擎：证据 → 根因 → 修复
├── fix_engine.py        # 修复执行、备份、journal、rollback
├── safety.py            # 命令分级、危险词过滤、sudo 审计
├── report.py            # Markdown/JSON 报告生成
├── kb.py                # 读取 final.md / rules/*.json 知识库
└── utils.py             # ANSI 剥离、超时子进程、JSON 输出
```

---

## 4. CLI 命令

```bash
# 一键看网络 + Codex 健康（最常用）
python3 netfix.py codex [--json]

# OSI 五层通用分诊
python3 netfix.py triage [--json]

# 代理核心专项
python3 netfix.py proxy [--json]

# 分项诊断
python3 netfix.py dns [域名] [--json]
python3 netfix.py wifi [--json]
python3 netfix.py ssl [域名] [--json]
python3 netfix.py connectivity [目标] [--json]

# 自动/半自动修复
python3 netfix.py fix --issue dns-cache [--dry-run]
python3 netfix.py fix --all [--dry-run]   # 对当前报告里的 Tier 1 全部执行

# 报告与回滚
python3 netfix.py report [--json]
python3 netfix.py rollback

# 知识库查询
python3 netfix.py kb --query "MTU"
```

---

## 5. 数据契约（JSON 报告）

```json
{
  "meta": {
    "version": "0.1.0",
    "timestamp": "2026-06-17T13:00:00+08:00",
    "platform": "darwin",
    "hostname": "qibaishi-mac"
  },
  "environment": {
    "gui_client": "v2rayN",
    "active_core": "xray",
    "mixed_port": 10808,
    "api_port": null,
    "tun_enabled": true,
    "system_proxy": {
      "http": "127.0.0.1:10808",
      "https": "127.0.0.1:10808",
      "socks": "127.0.0.1:10808",
      "pac": "http://wpad/wpad.dat"
    },
    "active_profile": {
      "id": "5559327888472053673",
      "remarks": "cc-http",
      "address": "direct.miyaip.online",
      "port": 8001,
      "type": "http"
    },
    "profiles": [
      {"remarks":"cc","address":"direct.miyaip.online","port":8001,"status":"untested"},
      {"remarks":"cc3","address":"63.124.160.52","port":8022,"status":"untested"},
      {"remarks":"cc-http","address":"direct.miyaip.online","port":8001,"status":"active"},
      {"remarks":"cc2","address":"direct.miyaip.online","port":8001,"status":"untested"}
    ]
  },
  "diagnostics": [
    {
      "name": "codex_api_direct",
      "status": "fail",
      "duration_ms": 5230,
      "details": {"error": "timeout", "target": "https://api.openai.com"}
    },
    {
      "name": "codex_api_via_proxy",
      "status": "ok",
      "duration_ms": 320,
      "details": {"http_code": 200, "exit_ip": "63.124.160.52"}
    }
  ],
  "root_causes": [
    {
      "id": "proxy-works-direct-blocked",
      "description": "直连无法访问 OpenAI，但经 127.0.0.1:10808 代理可通；代理当前正常。",
      "confidence": 0.95,
      "anchor": "final.md §9"
    }
  ],
  "fixes": [
    {
      "id": "flush-dns-cache",
      "tier": 1,
      "description": "刷新 macOS DNS 缓存",
      "command": "sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder",
      "verify": "scutil --dns",
      "auto": true
    }
  ],
  "manual_steps": [
    {
      "id": "switch-v2rayn-node",
      "description": "v2rayN 当前节点失效时手动切换",
      "steps": [
        "打开 v2rayN 主界面",
        "在节点列表双击 'cc2' 或 'cc3'",
        "等待底部延迟测试显示绿色数字",
        "重新跑 python3 netfix.py codex 验证"
      ]
    }
  ]
}
```

---

## 6. 安全分级（Tier）

| Tier | 名称 | 示例 | 默认行为 |
|---|---|---|---|
| 0 | 只读诊断 | `ping`、`dig`、`scutil --dns`、`lsof` | 自动执行 |
| 1 | 低风险自动修复 | DNS 缓存刷新、重连 Wi-Fi、清理证书缓存 | 自动执行；`--dry-run` 可预览 |
| 2 | 变更型修复需确认 | 改 `guiNConfig.json` 切换节点、改系统代理、改 hosts | 先备份 → 出 diff → 用户 `y/N`；支持 `--yes` 仅对 Tier 1 生效 |
| 3 | 仅手动清单 | GUI 里点按钮、路由器后台、服务商换密码 | 不执行，只输出精确步骤 |

---

## 7. 客户端适配策略

| 检测到的客户端 | 自动切换能力 | 实现方式 |
|---|---|---|
| **v2rayN (xray/sing-box)** | 不支持热切换 | 读 `guiNConfig.json` + `guiNDB.db`；测试各节点地址可达性；Tier 2 备份后改 `IndexId` 并提示重启；Tier 3 给出手动切换步骤 |
| **mihomo / Clash / Clash Verge** | 支持 | External Controller API：`/proxies`、`/proxies/{name}/delay`、`PUT /proxies/GLOBAL` |
| **sing-box (standalone)** | 部分支持 | 若配置 `experimental.clash_api`，走相同 API |
| **WireGuard App** | 不支持热切换 | 读隧道配置；Tier 2 改 `wg0.conf`；Tier 3 App 操作清单 |
| **Tailscale / ZeroTier** | 支持部分 | 各自 CLI (`tailscale status`) |

---

## 8. 缺失脚本补齐

新增 `bin/` 脚本：

| 脚本 | 作用 | 对应 final.md |
|---|---|---|
| `bin/codex-check.sh` | Codex/OpenAI/GitHub 可达性专项 | 新增 |
| `bin/mtu-tune.sh` | 自动探测并推荐 MTU | §1.4 / §10.3 |
| `bin/ipv6-leak-check.sh` | IPv6 泄漏检测与一键关闭 | §10.2 |
| `bin/mihomo-api-check.sh` | 检测 mihomo External Controller API 可用性 | 新增 |
| `bin/v2rayn-info.sh` | 读取 v2rayN 当前节点与配置 | 新增 |

同时给现有 `bin/*.sh` 增加 `--json` 输出模式，便于 `netfix` 解析。

---

## 9. 验证标准

1. `python3 netfix.py codex` 在**网络健康时**输出 `status: ok` 并给出当前出口 IP。
2. 手动把 v2rayN 切到一个无效节点后，`python3 netfix.py codex` 能检测失败、标记 `codex_api_via_proxy: fail`、推荐切换节点。
3. `python3 netfix.py codex --json` 的输出可以被另一个脚本用 `json.loads()` 直接解析。
4. `python3 netfix.py fix --issue flush-dns --dry-run` 只打印命令不执行；去掉 `--dry-run` 后执行并写入 journal。
5. `python3 netfix.py rollback` 能撤销上一次 Tier 2 变更。

---

## 10. 开源/产品化路径

- **仓库**：保留在 `/Users/qibaishi/Desktop/网络/`，未来可 push 到 GitHub 命名为 `netfix`。
- **License**：MIT。
- **README**：中英双语，突出“Codex 挂了先跑 netfix”。
- **社区**：用 `cases/` 目录收集真实故障 case，反哺规则库。
- **商业化可能**：付费 macOS GUI 版、节点健康 SaaS、企业审计版。
