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
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from threading import Lock, Thread
import asyncio
import ssl
import traceback

urllib3.disable_warnings()

BASE_PATH = os.path.expanduser("~/.hermes/workspace/mcloud2api")
TOKEN_FILE = os.path.join(BASE_PATH, "token.json")

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

    def ensure_valid(self):
        if self.load():
            self.save()
        if self.is_expired():
            return self.refresh()
        return True


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
        try:
            resp = requests.post(
                "https://ai.yun.139.com/api/openclaw/get",
                json={"sourceChannel": "522004", "userId": "1039848553440938503", "openclawId": "1305853487463928055"},
                headers=self.get_headers(),
                verify=False, timeout=30,
            ).json()
            return resp.get("data", {}).get("wsUrl")
        except Exception as e:
            print(f"Failed to get WS URL: {e}")
            return None

    async def ws_chat(self, message):
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
                await asyncio.wait_for(ws.recv(), timeout=5)

                # 发送消息 (JSON-RPC 格式)
                msg = {
                    "id": str(uuid.uuid4()),
                    "type": "req",
                    "method": "chat.send",
                    "params": {"message": message}
                }
                await ws.send(json.dumps(msg))

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
                                    answer = text
                            elif payload.get("stream") == "lifecycle":
                                if payload.get("data", {}).get("phase") == "end":
                                    break
                except asyncio.TimeoutError:
                    pass

                return {"answer": answer}
        except Exception as e:
            return {"error": str(e)}

    def chat(self, message):
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(self.ws_chat(message))
        loop.close()
        return result


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的 HTTP 服务器"""
    daemon_threads = True
    allow_reuse_address = True


class OpenAIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token_mgr = None
    ws_client = None

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}", flush=True)

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

    # ==================== 路由 ====================

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/v1/models":
                self.list_models()
            elif parsed.path.startswith("/v1/models/"):
                # GET /v1/models/{model_id}
                model_id = parsed.path.split("/")[-1]
                self.get_model(model_id)
            elif parsed.path == "/health":
                self.send_json({"status": "ok", "service": "mcloud2api"})
            elif parsed.path == "/":
                self.send_json({
                    "service": "mcloud2api",
                    "version": "1.0",
                    "endpoints": ["/", "/health", "/v1/models", "/v1/chat/completions", "/auth/set"],
                })
            # Ollama 兼容端点 - /api/tags
            elif parsed.path == "/api/tags":
                self.ollama_tags()
            else:
                self.send_json({"error": {"message": "Not found", "type": "not_found"}}, 404)
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"Error GET {self.path}: {e}")
            traceback.print_exc()

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            # 读取请求体用于调试
            length = int(self.headers.get("Content-Length", 0))
            body = b""
            if length > 0:
                body = self.rfile.read(length)
                print(f"[DEBUG] POST {self.path} body={body.decode('utf-8', errors='replace')[:500]}", flush=True)
            
            body_dict = {}
            if body:
                body_dict = json.loads(body.decode('utf-8', errors='replace'))
            
            if parsed.path == "/v1/chat/completions":
                self.chat_completion(body_dict)
            elif parsed.path == "/auth/set":
                self.set_auth()
            # Ollama 兼容端点
            elif parsed.path == "/api/show":
                self.ollama_show(body_dict)
            elif parsed.path == "/api/chat":
                self.ollama_chat(body_dict)
            elif parsed.path == "/api/generate":
                self.ollama_generate(body_dict)
            # 有些客户端用 POST /api/tags
            elif parsed.path == "/api/tags":
                self.ollama_tags()
            else:
                self.send_json({"error": {"message": "Not found", "type": "not_found"}}, 404)
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"Error POST {self.path}: {e}")
            traceback.print_exc()
            try:
                self.send_json({"error": {"message": str(e), "type": "server_error"}}, 500)
            except:
                pass

    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Max-Age", "3600")
            self.end_headers()
        except:
            pass

    # ==================== OpenAI API ====================

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

    def get_model(self, model_id):
        """GET /v1/models/{model_id} 获取单个模型信息"""
        # 查找匹配的模型
        for code, info in MODELS.items():
            openai_name = MCLAW_TO_OPENAI.get(code, code)
            if openai_name == model_id or code == model_id:
                # 返回请求的 ID，保持一致
                self.send_json({
                    "id": model_id,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "mclaw",
                    "root": code,
                    "parent": None,
                })
                return
        self.send_json({"error": {"message": "Model not found", "type": "not_found"}}, 404)

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

    def chat_completion(self, body=None):
        if body is None:
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
            if stream:
                self._sse_error(result["error"])
            else:
                self.send_json({"error": {"message": result["error"], "type": "server_error"}}, 500)
            return

        answer = result.get("answer", "[mclaw proxy] 未收到响应")
        chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        if stream:
            # SSE 流式响应
            self._send_streaming_response(chat_id, openai_model, answer)
        else:
            # 非流式响应
            response = {
                "id": chat_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": openai_model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": len(user_msg) // 4,
                    "completion_tokens": len(answer) // 4,
                    "total_tokens": len(user_msg) // 4 + len(answer) // 4
                },
            }
            self.send_json(response)

    def _send_streaming_response(self, chat_id, model, answer):
        """发送 SSE 流式响应"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # 发送 chunk
        chunk_size = 8
        for i in range(0, len(answer), chunk_size):
            chunk = answer[i:i+chunk_size]
            resp = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
            }
            self.wfile.write(f"data: {json.dumps(resp, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.01)

        # 发送结束 chunk
        final = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        self.wfile.write(f"data: {json.dumps(final, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        
        # 关闭连接
        self.close_connection = True

    def _sse_error(self, error_msg):
        """发送 SSE 错误"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(f"data: {json.dumps({'error': {'message': error_msg, 'type': 'server_error'}}, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    # ==================== Ollama 兼容 API ====================

    def ollama_tags(self):
        """Ollama /api/tags 兼容端点"""
        models = []
        for code, info in MODELS.items():
            openai_name = MCLAW_TO_OPENAI.get(code, code)
            models.append({
                "name": openai_name,
                "model": openai_name,
                "size": 0,
                "digest": "",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": code,
                    "families": [code],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0"
                }
            })
        self.send_json({"models": models})

    def ollama_show(self, body=None):
        """Ollama /api/show 兼容端点"""
        if body is None:
            body = self.read_body()
        model_name = body.get("name", "gpt-4")
        mclaw_code = OPENAI_TO_MCLAW.get(model_name, "blian_qwen37_plus")
        self.send_json({
            "modelfile": "",
            "parameters": "",
            "template": "",
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": mclaw_code,
                "families": [mclaw_code],
                "parameter_size": "7B",
                "quantization_level": "Q4_0"
            },
            "model_info": {}
        })

    def ollama_chat(self, body=None):
        """Ollama /api/chat 兼容端点"""
        if body is None:
            body = self.read_body()
        model_name = body.get("model", "gpt-4")
        messages = body.get("messages", [])

        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        result = self.ws_client.chat(user_msg)

        if "error" in result:
            self.send_json({"error": result["error"]}, 500)
            return

        answer = result.get("answer", "")
        self.send_json({
            "model": model_name,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "message": {"role": "assistant", "content": answer},
            "done": True
        })

    def ollama_generate(self, body=None):
        """Ollama /api/generate 兼容端点"""
        if isinstance(body, dict):
            body_dict = body
        else:
            body_dict = self.read_body()
        model_name = body_dict.get("model", "gpt-4")
        prompt = body_dict.get("prompt", "")

        result = self.ws_client.chat(prompt)

        if "error" in result:
            self.send_json({"error": result["error"]}, 500)
            return

        answer = result.get("answer", "")
        self.send_json({
            "model": model_name,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "response": answer,
            "done": True
        })


def main():
    import argparse
    parser = argparse.ArgumentParser(description="mcloud2api")
    parser.add_argument("-p", "--port", type=int, default=28943)
    parser.add_argument("-H", "--host", default="0.0.0.0")
    parser.add_argument("--phone", default="")
    parser.add_argument("--auth-token", default="")
    args = parser.parse_args()

    token_mgr = TokenManager()
    if args.phone and args.auth_token:
        token_mgr.set_token(args.phone, args.auth_token)
    else:
        if not token_mgr.load_from_leveldb():
            if not token_mgr.load():
                print("未找到 token，请使用 --phone 和 --auth-token 设置")

    ws_client = WSClient(token_mgr)

    OpenAIHandler.token_mgr = token_mgr
    OpenAIHandler.ws_client = ws_client

    server = ThreadingHTTPServer((args.host, args.port), OpenAIHandler)
    print(f"[mcloud2api] 监听于 http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mcloud2api] 关闭中...")
        server.shutdown()


if __name__ == "__main__":
    main()
