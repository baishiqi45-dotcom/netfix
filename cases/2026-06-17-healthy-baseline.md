# Case：健康网络基线

## 元信息

- **日期**：2026-06-17
- **症状**：网络正常，Codex / GitHub 均可达；本 case 作为健康基线参考。
- **客户端**：v2rayN（xray + sing-box）
- **节点类型**：HTTP 出口
- **最终根因**：无

## 关键证据

```bash
python3 netfix.py codex --timeout 8 --json
```

结论：

- 代理核心运行正常，mixed 端口 10808 监听。
- 系统代理已指向 127.0.0.1:10808。
- OpenAI API 可达（返回 401，说明网络路径正常，需 API key 才能调用）。
- GitHub / GitHub API 可达。
- 所有配置节点 TCP 层均可达。

## 修复过程

无需修复。此基线用于后续故障对比：当 Codex 不可用時，重跑同一命令，看哪一项从 ok 变成 fail/warn。

## 沉淀建议

- 保留此基线，方便快速 diff。
