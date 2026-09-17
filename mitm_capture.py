import json
from mitmproxy import http
import re

CAPTURE_FILE = "/home/tomac/.hermes/workspace/mcloud2api/capture.jsonl"

class TokenCapture:
    def request(self, flow):
        auth = flow.request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            entry = json.dumps({"auth": auth, "url": flow.request.pretty_url})
            with open(CAPTURE_FILE, "a") as f:
                f.write(entry + "\n")
        
        url = flow.request.pretty_url
        if "openclaw" in url.lower() or "mclaw" in url.lower() or "ws" in url.lower():
            print(f"[REQ] {flow.request.method} {url[:200]}", flush=True)
    
    def response(self, flow):
        try:
            body = flow.response.content.decode('utf-8', errors='replace')
            if 'openclaw' in body.lower() or 'mclaw' in body.lower() or 'wsUrl' in body:
                print(f"[RESP] {flow.request.pretty_url[:100]} -> {body[:500]}", flush=True)
        except:
            pass

addons = [TokenCapture()]
