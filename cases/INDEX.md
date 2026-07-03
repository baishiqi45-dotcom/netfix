# Netfix Case Index

这些 case 都应该是脱敏后的公开材料：不要出现真实代理、API Key、cookie、二维码、账号、客户信息或本机私有路径。

## 普通用户代理部署

- [普通用户第一次部署代理的 9 个坑](2026-06-29-普通用户代理部署体验审查.md)
  买了代理但不知道 Mac 上复制什么、粘贴哪里、怎么恢复原网络设置。适合作为 README 和发布帖的主故事。

## AI / 开发工具连不上

- [Codex 报连不上，其实是 API Key 失效](20260617-1405-codex-reachable-needs-key.md)
  网络层正常，但用户直觉以为是代理问题。Netfix 的价值是把错误层级先分清。

## 基线与复盘

- [健康基线快照](2026-06-17-healthy-baseline.md)
  网络健康时先留一份脱敏基线，下次故障可以做 before / after 对照。

## Add A New Case

1. 复制 [TEMPLATE.md](TEMPLATE.md)。
2. 写清触发场景、Netfix 关键输出、根因、实际修复、验证。
3. 确认没有真实密码、API Key、token、cookie、二维码、完整本机路径或真实代理地址。
4. 文件名使用 `YYYY-MM-DD-关键词.md`。
