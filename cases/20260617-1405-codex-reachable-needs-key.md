# Case

## 元信息

- **日期**：2026-06-17T14:05:34.598759+08:00
- **客户端**：v2rayN (v2rayN)
- **活动节点**：cc-http
- **症状**：OpenAI API 网络可达，返回 401 是因为缺少/无效 API key，不是网络故障

## 关键诊断

```json
{
  "diagnostics": [
    {
      "name": "openai_api",
      "target": "https://api.openai.com/v1/models",
      "proxy_used": "direct",
      "status": "warn",
      "http_code": 401,
      "duration_ms": 2281,
      "exit_ip": null,
      "error": "http error 401: unauthorized"
    },
    {
      "name": "openai_api",
      "target": "https://api.openai.com/v1/models",
      "proxy_used": "system",
      "status": "warn",
      "http_code": 401,
      "duration_ms": 1427,
      "exit_ip": null,
      "error": "http error 401: unauthorized"
    },
    {
      "name": "openai_api",
      "target": "https://api.openai.com/v1/models",
      "proxy_used": "127.0.0.1:10808",
      "status": "warn",
      "http_code": 401,
      "duration_ms": 1380,
      "exit_ip": null,
      "error": "http error 401: unauthorized"
    },
    {
      "name": "openai_chat",
      "target": "https://chat.openai.com/",
      "proxy_used": "direct",
      "status": "warn",
      "http_code": 308,
      "duration_ms": 1304,
      "exit_ip": null,
      "error": "http error 308: permanent redirect"
    },
    {
      "name": "openai_chat",
      "target": "https://chat.openai.com/",
      "proxy_used": "system",
      "status": "warn",
      "http_code": 308,
      "duration_ms": 1328,
      "exit_ip": null,
      "error": "http error 308: permanent redirect"
    },
    {
      "name": "openai_chat",
      "target": "https://chat.openai.com/",
      "proxy_used": "127.0.0.1:10808",
      "status": "warn",
      "http_code": 308,
      "duration_ms": 1336,
      "exit_ip": null,
      "error": "http error 308: permanent redirect"
    },
    {
      "name": "github",
      "target": "https://github.com/",
      "proxy_used": "direct",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 3244,
      "exit_ip": null,
      "error": null
    },
    {
      "name": "github",
      "target": "https://github.com/",
      "proxy_used": "system",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 3070,
      "exit_ip": null,
      "error": null
    },
    {
      "name": "github",
      "target": "https://github.com/",
      "proxy_used": "127.0.0.1:10808",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 3153,
      "exit_ip": null,
      "error": null
    },
    {
      "name": "github_api",
      "target": "https://api.github.com/",
      "proxy_used": "direct",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 1605,
      "exit_ip": null,
      "error": null
    },
    {
      "name": "github_api",
      "target": "https://api.github.com/",
      "proxy_used": "system",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 1313,
      "exit_ip": null,
      "error": null
    },
    {
      "name": "github_api",
      "target": "https://api.github.com/",
      "proxy_used": "127.0.0.1:10808",
      "status": "ok",
      "http_code": 200,
      "duration_ms": 1412,
      "exit_ip": null,
      "error": null
    },
    {
      "status": "ok",
      "details": {
        "mixed_port": 10808,
        "processes_checked": [
          "xray",
          "sing-box",
          "clash",
          "mihomo",
          "v2ray"
        ],
        "processes_running": true,
        "port_listening": true
      },
      "name": "proxy_core_status",
      "duration_ms": 103
    },
    {
      "status": "ok",
      "details": {
        "active_reachable": true,
        "profiles": [
          {
            "remarks": "cc",
            "address": "direct.miyaip.online",
            "port": 8001,
            "reachable": true
          },
          {
            "remarks": "cc3",
            "address": "63.124.160.52",
            "port": 8022,
            "reachable": true
          },
          {
            "remarks": "cc-http",
            "address": "direct.miyaip.online",
            "port": 8001,
            "reachable": true
          },
          {
            "remarks": "cc2",
            "address": "direct.miyaip.online",
            "port": 8001,
            "reachable": true
          }
        ]
      },
      "name": "node_reachability",
      "duration_ms": 21
    }
  ],
  "root_causes": [
    {
      "id": "codex-reachable-needs-key",
      "description": "OpenAI API 网络可达，返回 401 是因为缺少/无效 API key，不是网络故障",
      "confidence": 0.99
    }
  ]
}
```

## 修复过程

（待填写）

## 沉淀建议

（待填写：是否需要更新 rules/symptoms.json、bin 脚本或 final.md）
