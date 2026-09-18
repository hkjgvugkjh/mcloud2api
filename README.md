mcloud2api
---------

将中国移动云盘 mclaw (MobileClaw / 龙虾) API 转换为 OpenAI 兼容格式的本地代理。

基于对 `/opt/apps/com.cmic.mcloud` (v8.7.2) Electron 应用的逆向分析实现。

## 功能

- OpenAI `/v1/chat/completions` 兼容（stream + non-stream）
- OpenAI `/v1/models` 模型列表查询
- Ollama `/api/tags`, `/api/show`, `/api/chat`, `/api/generate` 兼容
- 自动从 Local Storage 读取/刷新 token
- 多线程 HTTP 服务器
- 模型路由（GPT-4 / Claude / DeepSeek / Qwen / Doubao）

## 安装

```bash
pip install -r requirements.txt
```

依赖：`requests`, `websockets`, `plyvel`

## 使用

### 方式一：自动从 Local Storage 读取（推荐）

如果你在本地运行过 mcloud 桌面客户端，token 会自动存储在 Local Storage 中。

```bash
# 启动时自动从 Local Storage 读取最新 token
python3 proxy.py -p 28943
```

### 方式二：手动指定

```bash
# 命令行参数
python3 proxy.py --phone 138xxxx --auth-token <your_token>

# API 设置
curl -X POST http://localhost:28943/auth/set \
  -H "Content-Type: application/json" \
  -d '{"phone": "138xxxx", "auth_token": "<your_token>"}'

# 环境变量
export MCLOUD_PHONE=138xxxx
export MCLOUD_AUTH_TOKEN=<your_token>
python3 proxy.py
```

### 方式三：一键启动（含 mitmproxy 拦截）

```bash
python3 start.py
```

启动后 mcloud 会弹出，登录后自动捕获 token。

### 调用示例

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

## Token 获取详解

### 方式一：从 Local Storage 自动读取（推荐）

mcloud 桌面客户端的 token 存储在 LevelDB 格式的 Local Storage 中。

**位置**：
```
~/.config/mcloud/Local Storage/leveldb/
```

**数据库文件**：
- `*.ldb` - 数据文件
- `*.log` - 日志文件

**存储格式**：
- Key: `_file://\x00\x01UserInfo`
- Value: `\x01` + JSON

**JSON 结构**：
```json
{
  "account": "138xxxx",
  "token": "gvS5Mc4y|1|RCS|1792206977965|...",
  "authToken": "oCjlO6df|1|RCS|1792206918040|...",
  "userDomainId": "1039848553440938503",
  "deviceid": "...",
  ...
}
```

**token 格式**：
```
gvS5Mc4y|1|RCS|1792206977965|base64signature
          ^   ^       ^            ^
        类型  版本   过期时间戳    签名
```

- 类型: `1` = RCS (Refresh Credential String)
- 有效期: 30 天 (2592000 秒)

**自动读取流程**：
1. 启动时 proxy.py 会尝试从 Local Storage 读取
2. 解析 UserInfo JSON 获取 authToken
3. 如果 token 即将过期（1小时内），自动调用 refresh 接口刷新

### 方式二：手动提取（脚本）

```bash
# 使用 Python 读取
python3 << 'EOF'
import plyvel, os, json

db_path = os.path.expanduser('~/.config/mcloud/Local Storage/leveldb')
if os.path.exists(os.path.join(db_path, 'LOCK')):
    os.remove(os.path.join(db_path, 'LOCK'))

db = plyvel.DB(db_path, create_if_missing=False, error_if_exists=False)
for key, value in db:
    key_str = key.decode('utf-8', errors='ignore')
    if 'UserInfo' in key_str and '_file://' in key_str:
        val = value.decode('utf-8', errors='ignore').lstrip('\x01')
        data = json.loads(val)
        print(f"Phone: {data['account']}")
        print(f"AuthToken: {data['authToken']}")
        print(f"Token: {data['token']}")
        # 计算过期时间
        parts = data['token'].split('|')
        if len(parts) >= 4:
            from datetime import datetime
            ts = int(parts[3]) / 1000
            print(f"Expire: {datetime.fromtimestamp(ts)}")
        break
db.close()
EOF
```

### 方式三：通过 mitmproxy 拦截

运行 `python3 start.py`，然后：
1. mitmproxy 会启动并监听 8080 端口
2. mcloud 通过代理启动
3. 在 mcloud 中完成登录
4. 按 Ctrl+C 停止捕获
5. token 自动保存到 `token.json`

### 方式四：从浏览器导出

如果你在网页版登录过：
1. 打开 `https://yun.139.com`
2. 开发者工具 → Application → Local Storage
3. 找到 `UserInfo` key
4. 复制 `authToken` 字段

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

## 许可证

仅供学习和研究使用。请遵守中国移动云盘的服务条款。
