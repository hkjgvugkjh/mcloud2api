#!/usr/bin/env python3
"""
mcloud2api - 一键启动脚本
功能: 启动 mitmproxy 拦截 mcloud 流量，自动捕获 token，启动 OpenAI 兼容代理
"""
import json
import time
import os
import subprocess
import sys
import base64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_FILE = os.path.join(BASE_DIR, "capture.jsonl")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
PROXY_PORT = 13080
MITM_PORT = 8080

def run(cmd, **kwargs):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)

def cleanup():
    run("pkill -9 -f mcloud")
    run("pkill -9 -f mitmdump")
    run("pkill -9 -f mitmproxy")
    time.sleep(1)

def main():
    print("=" * 60)
    print("mcloud2api - OpenAI 兼容代理")
    print("=" * 60)
    
    cleanup()
    
    # 创建 mitmproxy 插件 - 捕获 token
    plugin_code = '''
import json
from mitmproxy import http

CAPTURE_FILE = "{capture}"

class TokenCapture:
    def request(self, flow):
        auth = flow.request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            with open(CAPTURE_FILE, "a") as f:
                f.write(json.dumps({{"auth": auth, "url": flow.request.pretty_url}}) + "\\n")

addons = [TokenCapture()]
'''.format(capture=CAPTURE_FILE)
    
    plugin_path = os.path.join(BASE_DIR, "mitm_capture.py")
    with open(plugin_path, "w") as f:
        f.write(plugin_code)
    
    # 启动 mitmproxy
    print("\n[1] 启动 mitmproxy...")
    mitm = subprocess.Popen(
        ["mitmdump", "-p", str(MITM_PORT), "-s", plugin_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(2)
    
    # 启动 mcloud
    print("[2] 启动 mcloud（请等待登录完成）...")
    env = os.environ.copy()
    env["HTTP_PROXY"] = f"http://127.0.0.1:{MITM_PORT}"
    env["HTTPS_PROXY"] = f"http://127.0.0.1:{MITM_PORT}"
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    
    mcloud = subprocess.Popen(
        ["/opt/apps/com.cmic.mcloud/files/mcloud",
         f"--proxy-server=127.0.0.1:{MITM_PORT}",
         "--ignore-certificate-errors", "--no-sandbox"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd="/opt/apps/com.cmic.mcloud/files"
    )
    
    # 等待用户登录
    print("[3] 请在 mcloud 中完成登录，然后按 Ctrl+C 继续...")
    print("    等待中", end="", flush=True)
    
    try:
        while True:
            time.sleep(1)
            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n    继续...")
    
    # 读取捕获的 token
    print("[4] 读取捕获的 token...")
    token = None
    if os.path.exists(CAPTURE_FILE):
        with open(CAPTURE_FILE) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    auth = d.get("auth", "")
                    if auth.startswith("Basic "):
                        decoded = base64.b64decode(auth[6:]).decode()
                        parts = decoded.split(":")
                        if len(parts) >= 3:
                            token = {
                                "type": parts[0],  # pc 或 mobile
                                "phone": parts[1],
                                "auth_token": ":".join(parts[2:]),
                            }
                            break
                except:
                    pass
    
    if not token:
        print("    未捕获到 token!")
        mcloud.kill()
        mitm.kill()
        return
    
    # 保存 token
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)
    
    print(f"    已保存: phone={token['phone']}, type={token['type']}")
    
    # 清理
    mcloud.kill()
    mitm.kill()
    time.sleep(1)
    
    # 启动代理
    print(f"\n[5] 启动 OpenAI 兼容代理 (http://0.0.0.0:{PROXY_PORT})...")
    print(f"    手机: {token['phone']}")
    print(f"    模型: gpt-4 -> blian_qwen37_plus, deepseek -> blian_deepseek_v4_pro")
    print()
    print("测试命令:")
    print(f'  curl http://localhost:{PROXY_PORT}/v1/models')
    print(f'  curl http://localhost:{PROXY_PORT}/v1/chat/completions -H "Content-Type: application/json" -d \'{{"model":"gpt-4","messages":[{{"role":"user","content":"你好"}}]}}\'')
    print()
    
    # 启动代理
    proxy = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "proxy.py"),
         "-p", str(PROXY_PORT),
         "--phone", token["phone"],
         "--auth-token", token["auth_token"]]
    )
    
    try:
        proxy.wait()
    except KeyboardInterrupt:
        print("\n[6] 关闭中...")
        proxy.kill()

if __name__ == "__main__":
    main()
