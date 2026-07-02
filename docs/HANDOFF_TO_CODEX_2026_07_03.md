# Codex 接力提示 — Netfix 产品力第二轮

> 接手时间：2026-07-03
> 上轮 commit：`e961763 Polish installer UX, paste-proxy placeholder, and source-export path scrubbing`
> 当前分支：`main`（本地已提交，未 push；origin = `https://github.com/baishiqi45-dotcom/netfix.git`）

## 一、本轮做了什么（已落到 main）

### 用户体感改动
1. **`gui/macos/Sources/Views/ProxySetupView.swift`**：粘贴框 `TextEditor` 加了 placeholder（`例如 proxy.example.com:8001:用户名:密码`，列出支持格式 + 不支持的 ss/vmess/订阅链接）；副标题保留 `密码保存到本机密码库，不上传`（onboarding 测试 `test_proxy_setup_exposes_one_paste_proxy_onboarding_path` 要求）。
2. **`scripts/install_mac_app_from_github.sh`**：结尾 banner 重写为 4 块——✅ 安装完成 / 📦 App 路径 / 🍎 Gatekeeper 引导（"系统设置 → 隐私与安全性 → 仍要打开"）/ 🧹 卸载命令 / ⚠️ QA 警告。
3. **`scripts/install_mcp.sh`**：Kimi 段输出加 `====` 分隔块 + 完整 JSON `mcpServers` 配置 + 三宿主路径表（Kimi/Claude Desktop/Cursor）+ 中文引导。**保留** `"Automatic Kimi MCP registration is not enabled"` 字符串（`test_open_source_readiness.py` 硬约束）。

### 安全改动（修了一个真实 bug）
4. **`scripts/path_sanitizer.py`**：macOS 上 `/tmp` 是 `/private/tmp` 的 symlink。原 `path_forms` 只处理 `/private/var/` ↔ `/var/`，所以 `SOURCE-EXPORT-MANIFEST.json` 里 audit finding 的 `f"under {root}"` 字串会把 `/tmp/...` 形式泄漏到对外发布包。已加 `/private/tmp/` ↔ `/tmp/` 互转。

### 测试门禁
5. **`tests/test_install_scripts_user_experience.py`**：新增 6 个 UX 硬约束测试，覆盖 banner / 路径 / placeholder / 中英 README / Issue 模板。**不要删**。

## 二、验收记录（全部通过）

```
python3 -m pytest -q                → 424 passed, 1 skipped
python3 -m py_compile netfix/*.py   → ok
bash -n scripts/install_*.sh       → ok (3 个脚本)
python3 scripts/marketing_claims_check.py --json  → ok=true, 41 checked, 0 findings
python3 scripts/release_audit.py --scope workspace --root . --json  → ok=true, 0 findings
python3 scripts/source_export.py --zip --json  → ok=true, 204 files exported
git diff --check                    → ok
cd gui/macos && swift build         → Build complete! (4.79s)
```

## 三、上轮 Kimi/CLAUDE 审计还没解决的真缺口（按产品力排序）

1. **Apple Developer ID 签名 + 公证**（P0）—— 当前 QA DMG 仍然被 Gatekeeper 拦截，普通用户第一步就走不通。需要 Apple Developer ID 账号 + `xcrun notarytool submit` 脚本 + `.github/workflows/release.yml` 自动签名公证。
2. **真机 GIF + 截图**（P0）—— README 现在是概念图，star 转化差。3-5 个 GIF + 6 张截图覆盖"粘贴 → 预检 → 部署 → 失败 banner → Keychain → 卸载"。
3. **ProxySetupView 4 步线性 wizard**（Kimi #31/#32）—— 当前保存后"开始使用"按钮还是另起一行，应该做成同页 wizard；保存成功后自动高亮部署按钮。
4. **Dashboard "一键修复"按钮**（Kimi #39）—— error banner 当前只有"重试 / 复制错误 / 查看日志"，应复用 `explanationCard.primaryAction` 模式，加一键修复。
5. **SettingsView 6 Tab → 3 Tab**（Kimi #17）—— 合并为 常规 / AI / 高级 三个 Tab；proxy 折叠到常规；agent 折叠到高级；permissions 折叠到高级。
6. **`netfix_proxy_credential_doctor` MCP 工具**（CLAUDE §5.6）—— 当用户问"我代理怎么填"时，Agent 能给对话式引导 + dry-run + 预演，不是返回 JSON。
7. **`cases/INDEX.md` + 累积到 10 个脱敏真实 case**（Kimi §3 #13）—— 已有 3 个，目标 10 个覆盖代理部署 / AI 工具断线 / VPN 冲突 / DNS 污染。

## 四、不要做的事（防止重复 / 越权）

- **不要重写 README/AGENTS.md 首屏**——前两轮已经按 Kimi 审计 §1.5 / §2 改完，再改会跟 `test_open_source_readiness.py` 的字符串硬约束打架。
- **不要动 `redaction.py` / `safety.py` / `agent_tools.py` / `logs.py` / `proxy_bridge.py` 的 P0 修复**——都已验证。
- **不要拆 `residential_proxy.py` (2549 行) / `SettingsView.swift` (2421 行)**——大重构，本轮没动；v0.3.0 再做。
- **不要把 QA DMG 写成正式版**——README、scripts、Issue 模板里所有"QA / 未签名 / 未公证"警告都要保留。
- **不要 push 到 origin**——`main` 当前已提交但未 push；等用户明确授权 `git push origin main`。

## 五、需要决策的开放问题（问用户）

1. **是否 push 当前 commit 到 origin？** `e961763` 已落地本地 main，origin 是 `https://github.com/baishiqi45-dotcom/netfix.git`。
2. **是否要申请 Apple Developer ID 签名？** 这是把 Netfix 从"技术测试版"变成"普通小白正式版"的唯一硬门槛，需要用户决定是否投入 Apple Developer Program 年费。
3. **是否要开始做"真机 GIF + 截图"？** 截图素材要先在干净 macOS QA 机器上跑 Netfix.app 才能截，需要用户授权 / 提供环境。

## 六、接力时第一步做什么

```bash
# 1) 拉最新
cd /Users/qibaishi/Desktop/网络
git pull origin main  # 仅在已 push 后

# 2) 跑硬门禁确认基线
python3 -m pytest -q
python3 scripts/marketing_claims_check.py --json
python3 scripts/release_audit.py --scope workspace --root . --json

# 3) 决定本轮重点：优先做 §三 的 1（签名公证）或 3（wizard）或 5（Tab 合并）
```

接力前请读：
- `docs/KIMI_DOMESTIC_PRODUCT_GROWTH_AUDIT_2026_07_02.md`（国内用户 + 增长）
- `docs/CLAUDE_NEXT_PRODUCT_DEEP_AUDIT_2026_07_02.md`（技术 + 安全 + MCP schema）
- `docs/github/STAR_GUIDE.md`（star 前硬门禁清单）