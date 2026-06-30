# Case 模板

> 每次真实网络故障修复后，复制本模板创建新 case，帮助 netfix 规则库持续进化。

## 元信息

- **日期**：YYYY-MM-DD HH:MM
- **症状**：一句话描述用户看到的故障（如 "Codex 突然不补全" / "网页打不开"）
- **客户端**：v2rayN / Clash Verge / Mihomo Party / WireGuard / ...
- **节点类型**：VMess / VLESS / Trojan / SOCKS / HTTP / Hysteria2 / ...
- **最终根因**：定位到哪一层（代理 / DNS / Wi-Fi / SSL / 防火墙 / 系统代理）

## 关键证据

粘贴 `python3 netfix.py codex --json` 中关键诊断项：

```json
{
  "diagnostics": []
}
```

## 修复过程

1. 先跑了什么命令
2. 看到了什么输出
3. 最终怎么修好的

## 沉淀建议

- 是否需要新增/修改 `rules/symptoms.json`？
- 是否需要新增 `bin/*.sh` 诊断脚本？
- 是否需要更新 `final.md` 某章节？
