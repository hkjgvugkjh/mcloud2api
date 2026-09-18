mcloud2api
---------

将中国移动云盘 mclaw (MobileClaw / 龙虾) API 转换为 OpenAI 兼容格式的本地代理。

基于对 `/opt/apps/com.cmic.mcloud` (v8.7.2) Electron 应用的逆向分析实现。

## 功能

- OpenAI `/v1/chat/completions` 兼容（stream + non-stream）
- OpenAI `/v1/models` 模型列表查询
- Ollama `/api/tags`, `/api/show`, `/api/chat`, `/api/generate` 兼容
- 自动 token 刷新（30天有效期）
- 多线程 HTTP 服务器
- 模型路由（GPT-4 / Claude / DeepSeek / Qwen / Doubao）

## 安装

```bash
pip install -r requirements.txt
```

依赖：`requests`, `websockets`

## 使用

### 1. 设置认证

```bash
# 方式一：命令行参数
python3 proxy.py --phone 138xxxx --auth-token <your_token>

# 方式二：API
curl -X POST http://localhost:28943/auth/set \
  -H "Content-Type: application/json" \
  -d '{"phone": "138xxxx", "auth_token": "<your_token>"}'

# 方式三：环境变量
export MCLOUD_PHONE=138xxxx
export MCLOUD_AUTH_TOKEN=<your_token>
python3 proxy.py
```

### 2. 启动代理

```bash
python3 proxy.py -p 28943
```

### 3. 调用示例

```bash
# 聊天
curl http://localhost:28943/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-reasoner",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'

# 流式响应
curl -N http://localhost:28943/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "blian_deepseek_v4_pro",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

## 模型映射

| OpenAI 模型名 | mclaw 模型 | 实际模型 |
|--------------|-----------|---------|
| `deepseek-reasoner` / `deepseek-chat` | `blian_deepseek_v4_pro` | DeepSeek-V4-Pro |
| `qwen-plus` | `blian_qwen37_plus` | 通义 qwen3.7-plus |
| `qwen-max` | `blian_qwen36_plus` | 通义 qwen3.6-plus |
| `qwen-turbo` | `blian_qwen35_plus` | 通义 qwen3.5-plus |
| `gpt-4` / `gpt-4o` / `claude-3-5-sonnet` | `blian_qwen37_plus` | 通义 qwen3.7-plus |
| `gpt-4o-mini` / `claude-3-haiku` | `vlm_huoshan_2_0_mini_thinking_vision` | 豆包-Seed-2.0-Mini |
| `doubao-pro` | `vlm_huoshan_2_0_lite_thinking_vision` | 豆包-Seed-2.0-Lite |
| `doubao-lite` | `vlm_huoshan_2_0_mini_thinking_vision` | 豆包-Seed-2.0-Mini |

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/health` | GET | 健康检查 |
| `/v1/models` | GET | 模型列表 |
| `/v1/models/{id}` | GET | 单个模型信息 |
| `/v1/chat/completions` | POST | OpenAI 聊天完成 |
| `/auth/set` | POST | 设置认证信息 |
| `/api/tags` | GET | Ollama 模型列表 |
| `/api/show` | POST | Ollama 模型详情 |
| `/api/chat` | POST | Ollama 聊天 |
| `/api/generate` | POST | Ollama 文本生成 |

## 配置为 Hermes Agent 的 custom provider

在 `~/.hermes/config.yaml` 中:

```yaml
model:
  default: blian_deepseek_v4_pro
  provider: custom:mcloud2api

custom_providers:
  - name: mcloud2api
    base_url: http://localhost:28943/v1
    api_key: "nokey"
    model: blian_qwen37_plus
    api_mode: chat_completions
    discover_models: true
```

## Token 获取

token 存储在中国移动云盘的 Local Storage 中。

获取方式：通过 mitmproxy 拦截 mcloud 应用的网络请求，或从浏览器导出的 Local Storage 中提取。

## 许可证

仅供学习和研究使用。请遵守中国移动云盘的服务条款。
