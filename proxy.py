#!/usr/bin/env python3
"""
mcloud2api - OpenAI 兼容代理
将中国移动云盘 mclaw (MobileClaw) API 转换为 OpenAI 格式
"""
import json
import requests
import uuid
import time
import os
import sys
import base64
import urllib3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Lock
import asyncio
import ssl

urllib3.disable_warnings()

BASE_PATH = os.path.expanduser("~/.hermes/workspace/mcloud2api")
TOKEN_FILE = os.path.join(BASE_PATH, "token.json")
WS_URL_FILE = os.path.join(BASE_PATH, "ws_url.txt")

MODELS = {
    "blian_qwen37_plus": {"name": "通义qwen3.7-plus"},
    "blian_qwen36_plus": {"name": "通义qwen3.6-plus"},
    "blian_qwen35_plus": {"name": "通义qwen3.5-plus"},
    "vlm_huoshan_2_0_lite_thinking_vision": {"name": "豆包-Seed-2.0-Lite"},
    "vlm_huoshan_2_0_mini_thinking_vision": {"name": "豆包-Seed-2.0-Mini"},
    "blian_deepseek_v4_pro": {"name": "DeepSeek-V4-Pro"},
}

OPENAI_TO_MCLAW = {
    "gpt-4": "blian_qwen37_plus",
    "gpt-4o": "blian_qwen37_plus",
    "gpt-4o-mini": "vlm_huoshan_2_0_mini_thinking_vision",
    "claude-3-5-sonnet": "blian_qwen37_plus",
    "claude-3-opus": "blian_qwen37_plus",
    "claude-3-haiku": "vlm_huoshan_2_0_mini_thinking_vision",
    "deepseek-chat": "blian_deepseek_v4_pro",
    "deepseek-reasoner": "blian_deepseek_v4_pro",
    "qwen-plus": "blian_qwen37_plus",
    "qwen-turbo": "blian_qwen35_plus",
    "qwen-max": "blian_qwen36_plus",
    "doubao-pro": "vlm_huoshan_2_0_lite_thinking_vision",
    "doubao-lite": "vlm_huoshan_2_0_mini_thinking_vision",
}

MCLAW_TO_OPENAI = {v: k for k, v in OPENAI_TO_MCLAW.items()}


class TokenManager:
    def __init__(self):
        self.token_file = TOKEN_FILE
        self.token = None
        self.phone = None
        self.auth_token = None
        self.expire_time = 0

    def load(self):
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file) as f:
                    data = json.load(f)
                self.token = data.get("token")
                self.phone = data.get("phone")
                self.auth_token = data.get("auth_token")
                self.expire_time = data.get("expire_time", 0)
                return True
            except:
                pass
        return False

    def save(self):
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "w") as f:
            json.dump({
                "token": self.token,
                "phone": self.phone,
                "auth_token": self.auth_token,
                "expire_time": self.expire_time,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, f, ensure_ascii=False, indent=2)

    def get_basic_auth(self):
        if not self.auth_token or not self.phone:
            return None
        return "Basic " + base64.b64encode(f"pc:{self.phone}:{self.auth_token}".encode()).decode()

    def set_token(self, phone, auth_token, expire_seconds=2592000):
        self.phone = phone
        self.auth_token = auth_token
        self.token = auth_token
        self.expire_time = time.time() + expire_seconds
        self.save()

    def is_expired(self):
        return time.time() >= (self.expire_time - 3600)

    def refresh(self):
        if not self.auth_token:
            if not self.load():
                return False
        if not self.is_expired():
            return True
        auth = self.get_basic_auth()
        if not auth:
            return False
        try:
            resp = requests.post(
                "https://user-njs.yun.139.com/user/auth/refreshToken",
                json={"authToken": self.auth_token},
                headers={"Authorization": auth, "Content-Type": "application/json"},
                verify=False, timeout=30,
            )
            data = resp.json()
            if data.get("code") == "0000" and data.get("data"):
                new_token = data["data"].get("token", self.auth_token)
                self.set_token(self.phone, new_token, 2592000)
                return True
            return False
        except Exception as e:
            print(f"Token refresh error: {e}")
            return False


class WSClient:
    """WebSocket 聊天客户端"""
    
    def __init__(self, token_mgr):
        self.token_mgr = token_mgr
        self.ws_url = None
        self.lock = Lock()
    
    def get_headers(self):
        auth = self.token_mgr.get_basic_auth()
        return {
            "Host": "ai.yun.139.com",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://appmail.mail.10086.cn",
            "Referer": "https://appmail.mail.10086.cn/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) mcloud/8.7.2 Chrome/108.0.5359.215 Electron/22.3.0 Safari/537.36",
            "x-yun-api-version": "v1",
            "x-yun-app-channel": "522004",
            "x-yun-client-info": "4||30|||||||1920/1080|zh-CN|||",
            "Authorization": auth,
        }
    
    def get_ws_url(self):
        """获取 WS URL"""
        try:
            req = self._post("/api/openclaw/get", {
                "sourceChannel": "522004",
                "userId": "1039848553440938503",
                "openclawId": "1305853487463928055"
            })
            ws_url = req.get("data", {}).get("wsUrl")
            return ws_url
        except Exception as e:
            print(f"Failed to get WS URL: {e}")
            return None
    
    def _post(self, path, body):
        resp = requests.post(
            f"https://ai.yun.139.com{path}",
            json=body,
            headers=self.get_headers(),
            verify=False,
            timeout=30,
        )
        return resp.json()
    
    async def ws_chat(self, message):
        """通过 WebSocket 发送聊天消息"""
        import websockets
        
        ws_url = self.get_ws_url()
        if not ws_url:
            return {"error": "Failed to get WS URL"}
        
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        try:
            async with websockets.connect(
                ws_url, max_size=10*1024*1024, ssl=ssl_ctx,
                additional_headers={
                    "Origin": "https://appmail.mail.10086.cn",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                }
            ) as ws:
                # 等待 hello-ok
                await asyncio.wait_for(ws.recv(), timeout=5)
                
                # 发送消息 (JSON-RPC 格式)
                msg = {
                    "id": str(uuid.uuid4()),
                    "type": "req",
                    "method": "chat.send",
                    "params": {"message": message}
                }
                await ws.send(json.dumps(msg))
                
                # 收集响应
                answer = ""
                try:
                    while True:
                        resp = await asyncio.wait_for(ws.recv(), timeout=60)
                        d = json.loads(resp)
                        
                        if d.get("type") == "event" and d.get("event") == "agent":
                            payload = d.get("payload", {})
                            if payload.get("stream") == "assistant":
                                text = payload.get("data", {}).get("text")
                                if text:
                                    answer = text  # 取最新完整文本
                            elif payload.get("stream") == "lifecycle":
                                if payload.get("data", {}).get("phase") == "end":
                                    break
                except asyncio.TimeoutError:
                    pass
                
                return {"answer": answer}
        except Exception as e:
            return {"error": str(e)}
    
    def chat(self, message):
        """同步调用"""
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(self.ws_chat(message))
        loop.close()
        return result


class OpenAIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token_mgr = None
    ws_client = None

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return json.loads(self.rfile.read(length))
        return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/v1/models":
            self.list_models()
        elif parsed.path == "/health":
            self.send_json({"status": "ok", "service": "mcloud2api"})
        elif parsed.path == "/":
            self.send_json({
                "service": "mcloud2api",
                "version": "1.0",
                "endpoints": ["/", "/health", "/v1/models", "/v1/chat/completions", "/auth/set"],
            })
        else:
            self.send_json({"error": {"message": "Not found", "type": "not_found"}}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/v1/chat/completions":
            self.chat_completion()
        elif parsed.path == "/auth/set":
            self.set_auth()
        else:
            self.send_json({"error": {"message": "Not found", "type": "not_found"}}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "3600")
        self.end_headers()

    def set_auth(self):
        body = self.read_body()
        phone = body.get("phone", "")
        auth_token = body.get("auth_token", "")
        expire = body.get("expire_seconds", 2592000)
        if not phone or not auth_token:
            self.send_json({"error": "phone and auth_token required"}, 400)
            return
        self.token_mgr.set_token(phone, auth_token, expire)
        self.send_json({"status": "ok", "phone": phone, "expire_time": self.token_mgr.expire_time})

    def list_models(self):
        try:
            resp = requests.post("https://ai.yun.139.com/api/openclaw/config/get",
                json={"sourceChannel": "522004", "userId": "", "openclawId": "1305853487463928055"},
                headers=self._get_headers(), verify=False, timeout=30)
            data = resp.json()
            model_list = data.get("data", {}).get("modelList", []) if data.get("success") else []
        except:
            model_list = []

        models = []
        for m in model_list:
            code = m.get("code", "")
            openai_name = MCLAW_TO_OPENAI.get(code, code)
            models.append({
                "id": openai_name, "object": "model", "created": int(time.time()),
                "owned_by": "mclaw", "root": code, "parent": None,
            })

        if not models:
            for code in MODELS:
                models.append({
                    "id": code, "object": "model", "created": int(time.time()),
                    "owned_by": "mclaw", "root": code, "parent": None,
                })

        self.send_json({"object": "list", "data": models})

    def _get_headers(self):
        auth = self.token_mgr.get_basic_auth()
        return {
            "Host": "ai.yun.139.com",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://appmail.mail.10086.cn",
            "Referer": "https://appmail.mail.10086.cn/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) mcloud/8.7.2 Chrome/108.0.5359.215 Electron/22.3.0 Safari/537.36",
            "x-yun-api-version": "v1",
            "x-yun-app-channel": "522004",
            "x-yun-client-info": "4||30|||||||1920/1080|zh-CN|||",
            "Authorization": auth,
        }

    def chat_completion(self):
        body = self.read_body()
        openai_model = body.get("model", "gpt-4")
        messages = body.get("messages", [])
        stream = body.get("stream", False)

        # 提取用户消息
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        mclaw_model = OPENAI_TO_MCLAW.get(openai_model, "blian_qwen37_plus")

        # 通过 WS 发送聊天
        result = self.ws_client.chat(user_msg)

        if "error" in result:
            self.send_json({"error": {"message": result["error"], "type": "server_error"}}, 500)
            return

        answer = result.get("answer", "[mclaw proxy] 未收到响应")

        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": openai_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(user_msg) // 4,
                "completion_tokens": len(answer) // 4,
                "total_tokens": len(user_msg) // 4 + len(answer) // 4
            },
        }
        self.send_json(response)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="mcloud2api")
    parser.add_argument("-p", "--port", type=int, default=13080)
    parser.add_argument("-H", "--host", default="0.0.0.0")
    parser.add_argument("--phone", default="")
    parser.add_argument("--auth-token", default="")
    args = parser.parse_args()

    token_mgr = TokenManager()
    if args.phone and args.auth_token:
        token_mgr.set_token(args.phone, args.auth_token)
    else:
        if not token_mgr.load():
            print("未找到 token，请使用 --phone 和 --auth-token 设置")

    ws_client = WSClient(token_mgr)

    OpenAIHandler.token_mgr = token_mgr
    OpenAIHandler.ws_client = ws_client

    server = HTTPServer((args.host, args.port), OpenAIHandler)
    print(f"[mcloud2api] 监听于 http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mcloud2api] 关闭中...")
        server.shutdown()


if __name__ == "__main__":
    main()
