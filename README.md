# mcloud2api

将中国移动云盘 mclaw (MobileClaw) API 转换为 OpenAI 兼容格式的代理服务。

## 功能特性

- **OpenAI 兼容接口** — 支持 `/v1/models` 和 `/v1/chat/completions`
- **自动 Token 刷新** — 从 `~/.config/mcloud` 读取并自动刷新
- **WebSocket 聊天** — 完整实现 JSON-RPC 聊天协议
- **6 个 AI 模型** — 通义千问、豆包、DeepSeek 等
- **零配置启动** — 自动检测 mcloud 登录状态

## 环境要求

### 系统依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | >= 3.10 | 运行环境 |
| pip | >= 21.0 | 包管理器 |
| mcloud | >= 8.7.0 | 中国移动云盘客户端（已登录） |

### Python 依赖

```
requests>=2.28.0
websockets>=11.0
plyvel>=1.5.0
```

安装命令：
```bash
pip install -r requirements.txt
```

### 系统依赖（plyvel）

plyvel 需要 LevelDB 开发库：

```bash
# Ubuntu/Debian
sudo apt install libleveldb-dev

# CentOS/RHEL
sudo yum install leveldb-devel

# Arch Linux
sudo pacman -S leveldb
```

## 快速开始

### 1. 安装

```bash
git clone <repository-url>
cd mcloud2api
pip install -r requirements.txt
```

### 2. 配置

确保 mcloud 已登录（正常使用一次云盘客户端即可）。

Token 会自动从以下位置读取：
- `~/.config/mcloud/Local Storage/leveldb` (LevelDB 数据库)

### 3. 启动

```bash
# 方式一：直接启动
python3 proxy.py

# 方式二：指定端口
python3 proxy.py -p 8080

# 方式三：手动指定 token（如果自动检测失败）
python3 proxy.py --phone 13815206006 --auth-token <your_token>
```

### 4. 测试

```bash
# 健康检查
curl http://localhost:13080/health

# 列出模型
curl http://localhost:13080/v1/models

# 聊天
curl http://localhost:13080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"你好"}]}'
```

## 使用 OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:13080/v1",
    api_key="mclaw"  # 任意值即可
)

# 聊天
resp = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}]
)
print(resp.choices[0].message.content)

# 流式聊天
for chunk in client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## API 参考

### GET /health

健康检查。

**响应示例**：
```json
{"status": "ok", "service": "mcloud2api"}
```

### GET /v1/models

列出可用模型。

**响应示例**：
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1789625856,
      "owned_by": "mclaw",
      "root": "blian_qwen37_plus",
      "parent": null
    }
  ]
}
```

### POST /v1/chat/completions

聊天接口（OpenAI 兼容）。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | 模型名称（见模型映射表） |
| messages | array | 是 | 对话消息列表 |
| stream | boolean | 否 | 是否流式输出（暂未实现） |
| temperature | number | 否 | 温度参数（暂未生效） |
| max_tokens | integer | 否 | 最大 token 数（暂未生效） |

**请求示例**：
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "你是一个助手"},
    {"role": "user", "content": "你好"}
  ]
}
```

**响应示例**：
```json
{
  "id": "chatcmpl-8692925f225241dba67192c1",
  "object": "chat.completion",
  "created": 1789625856,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！有什么可以帮你的吗？😊"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 10,
    "total_tokens": 15
  }
}
```

### POST /auth/set

手动设置认证信息。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| phone | string | 是 | 手机号 |
| auth_token | string | 是 | authToken |
| expire_seconds | integer | 否 | 过期秒数（默认 2592000） |

## 模型映射

| OpenAI 模型名 | mclaw 模型代码 | 说明 |
|---|---|---|
| gpt-4 | blian_qwen37_plus | 通义 qwen3.7-plus |
| gpt-4o | blian_qwen37_plus | 通义 qwen3.7-plus |
| gpt-4o-mini | vlm_huoshan_2_0_mini_thinking_vision | 豆包 Seed-2.0-Mini |
| claude-3-5-sonnet | blian_qwen37_plus | 通义 qwen3.7-plus |
| claude-3-opus | blian_qwen37_plus | 通义 qwen3.7-plus |
| claude-3-haiku | vlm_huoshan_2_0_mini_thinking_vision | 豆包 Seed-2.0-Mini |
| deepseek-chat | blian_deepseek_v4_pro | DeepSeek-V4-Pro |
| deepseek-reasoner | blian_deepseek_v4_pro | DeepSeek-V4-Pro |
| qwen-plus | blian_qwen37_plus | 通义 qwen3.7-plus |
| qwen-turbo | blian_qwen35_plus | 通义 qwen3.5-plus |
| qwen-max | blian_qwen36_plus | 通义 qwen3.6-plus |
| doubao-pro | vlm_huoshan_2_0_lite_thinking_vision | 豆包 Seed-2.0-Lite |
| doubao-lite | vlm_huoshan_2_0_mini_thinking_vision | 豆包 Seed-2.0-Mini |

## 技术架构

### Token 刷新机制

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  mcloud     │────▶│  LevelDB         │────▶│  TokenManager   │
│  客户端     │     │  (UserInfo)      │     │                 │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────┐
│  POST https://user-njs.yun.139.com/user/auth/refreshToken  │
│  Body: {"authToken": "<current>"}                          │
│  Header: Authorization: Basic base64("pc:phone:token")     │
└─────────────────────────────────────────────────────────────┘
```

**Token 格式**：
- 认证头：`Authorization: Basic base64("pc:{phone}:{authToken}")`
- 有效期：30 天（2592000 秒）
- 自动刷新：过期前 1 小时

### WebSocket 聊天协议

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Client     │────▶│  /api/openclaw/  │────▶│  WS URL         │
│             │     │  get             │     │  (wss://...)    │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────┐
│  WebSocket: wss://mclaw.yun.139.com/ai/channel/openclaw-*  │
│  Origin: https://appmail.mail.10086.cn                     │
└─────────────────────────────────────────────────────────────┘
```

**消息格式（JSON-RPC）**：

发送：
```json
{
  "id": "<uuid>",
  "type": "req",
  "method": "chat.send",
  "params": {"message": "你好"}
}
```

接收：
```json
// 确认
{"type": "res", "id": "...", "ok": true, "payload": {"runId": "..."}}

// 内容流
{"type": "event", "event": "agent", "payload": {"stream": "assistant", "data": {"text": "..."}}}

// 结束
{"type": "event", "event": "agent", "payload": {"stream": "lifecycle", "data": {"phase": "end"}}}
```

### 请求头（关键）

所有 API 请求需要以下头部：

```
x-yun-api-version: v1
x-yun-app-channel: 522004
x-yun-client-info: 4||30|||||||1920/1080|zh-CN|||
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) mcloud/8.7.2 Chrome/108.0.5359.215 Electron/22.3.0 Safari/537.36
Origin: https://appmail.mail.10086.cn
Referer: https://appmail.mail.10086.cn/
```

## 文件结构

```
mcloud2api/
├── proxy.py              # 主程序（OpenAI 兼容代理）
├── token_manager.py      # Token 管理（LevelDB 读取 + 自动刷新）
├── mitm_capture.py       # mitmproxy token 捕获插件
├── mitm_ws_hook.py       # mitmproxy WS 拦截插件
├── start.py              # 一键启动脚本
├── requirements.txt      # Python 依赖
├── README.md             # 说明文档
└── token.json            # Token 缓存（自动生成）
```

## 配置说明

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-p, --port` | 13080 | 监听端口 |
| `-H, --host` | 0.0.0.0 | 监听地址 |
| `--phone` | (空) | 手机号（可选） |
| `--auth-token` | (空) | authToken（可选） |

### 环境变量

| 变量 | 说明 |
|------|------|
| `MCLOUD_TOKEN_FILE` | token.json 路径 |
| `MCLOUD_LEVELDB_PATH` | LevelDB 路径 |

## 故障排除

### Token 读取失败

**症状**：`未找到 token，请使用 --phone 和 --auth-token 设置`

**解决**：
1. 确保 mcloud 已登录
2. 检查 `~/.config/mcloud/Local Storage/leveldb` 是否存在
3. 手动指定 `--phone` 和 `--auth-token`

### API 返回 "资源不存在"

**症状**：`{"success":false,"code":"01000005","message":"资源不存在"}`

**解决**：
1. 检查请求头是否完整（特别是 `User-Agent` 和 `x-yun-client-info`）
2. 确认 sourceChannel 为 `522004`

### WebSocket 连接失败

**症状**：`HTTP 401` 或 `InvalidStatus`

**解决**：
1. 确认 WS URL 中的 `auth_token` 参数完整
2. 添加 `Origin: https://appmail.mail.10086.cn` 头

### plyvel 安装失败

**症状**：`Error: libleveldb-dev not found`

**解决**：
```bash
sudo apt install libleveldb-dev
```

## 开发历史

### v1.0.0 (2026-09-17)

- ✅ 初始版本
- ✅ Token 自动刷新
- ✅ REST API 代理
- ✅ WebSocket 聊天
- ✅ 6 个 AI 模型支持

## 许可证

MIT License

## 免责声明

本项目仅供学习研究使用，请遵守中国移动云盘的服务条款。
