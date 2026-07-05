# Netfix P1/P2 网络洞察升级 Goal

> 日期：2026-07-05  
> 输入：P0 落地报告、Claude/Kimi/子智能体只读审查、当前 `main` 代码状态。  
> 目标：把 Netfix 从“单次诊断工具”升级成“能记住最近卡顿、看出谁占用网络、解释代理健康趋势”的本地 App。

## 设计判断

这轮不再扩复杂页面。所有新增洞察收进现有 Dashboard 的“实时响应”卡，Settings 只加“卡顿检测与隐私”。

## P1 必须落地

1. `GET /dashboard/insights`
   - 返回当前后台网络占用 Top 3。
   - 返回最近 5 次卡顿事件。
   - 返回代理近 10 次健康趋势。

2. 本地轻量采样
   - 默认不偷偷常驻。
   - 用户开启后每 5 分钟轻量采样一次。
   - 健康样本只放内存；只有卡顿事件才写入 `events.jsonl`。

3. 卡顿事件
   - 只保存进程名/友好名、方向、粗略速度桶、延迟/响应摘要。
   - 不保存 URL、远端 IP、网页内容、聊天内容、代理密码。

4. 代理健康趋势
   - 复用 `proxy_monitor` 事件。
   - 趋势只暴露 status、latency、auth、error_code。
   - 不暴露 `target`、`checked_via`、proxy host、出口 IP。

5. “哪些 App 不提醒我”
   - 设置在 `settings.json`，不是日志。
   - 非 regex，大小写不敏感 substring。
   - Dashboard 的 Top 3 行提供“别再提醒这个 App”。

## P2 本轮只做最小安全部分

1. Wi-Fi SNR
   - 在 `wifi_signal` 中计算 `snr = rssi - noise`。
   - 不在事件里持久化 SSID/BSSID。

2. 网关拥塞
   - 本轮只保留设计，不宣称精准识别路由器拥塞。
   - 未来需要连续两次第一跳 RTT/loss 异常且网络质量差，才给“路由器/网关可能拥堵”。

3. before/after GIF
   - 不在本轮造假截图。
   - 等真实场景复现后再录。

## API 形状

- `GET /settings/network-activity`
- `POST /settings/network-activity`
- `GET /network/monitor`
- `POST /network/monitor/start`
- `POST /network/monitor/stop`
- `GET /timeline/lag`
- `GET /proxy/monitor/trend`
- `GET /dashboard/insights`

## 验收

- `python3 -m pytest -q`
- `python3 -m py_compile netfix/*.py netfix/layers/*.py`
- `bash -n scripts/install_mcp.sh scripts/install_mac_app_from_github.sh scripts/install_codex_mcp_from_github.sh`
- `python3 scripts/marketing_claims_check.py --json`
- `python3 scripts/release_audit.py --scope workspace --root . --json`
- `python3 scripts/source_export.py --zip --json`
- `git diff --check`
- `cd gui/macos && swift build`

## 非目标

- 不做 Activity Monitor 替代品。
- 不抓包，不解 TLS。
- 不保存 URL、远端 IP、聊天内容。
- 不做节点质量评分、平台通过率、风控相关承诺。
- 不把 P2 的网关拥塞说成已经精确识别。
