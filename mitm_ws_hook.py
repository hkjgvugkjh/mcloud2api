import json
from mitmproxy import http
import re

CAPTURE_FILE = "/home/tomac/.hermes/workspace/mcloud2api/capture.jsonl"

INJECT_JS = b"""
<script data-ws-hook>
(function() {
    if (window.__wsHooked) return;
    window.__wsHooked = true;
    window.__wsMessages = [];
    const OrigWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        console.log('[WS-HOOK] Connect:', url);
        const ws = protocols ? new OrigWebSocket(url, protocols) : new OrigWebSocket(url);
        ws.__url = url;
        ws.__messages = [];
        
        const origSend = ws.send.bind(ws);
        ws.send = function(data) {
            const entry = {ts: Date.now(), dir: 'OUT', url: ws.__url, data: null};
            try { entry.data = typeof data === 'string' ? data.slice(0, 2000) : '[binary]'; } catch(e) {}
            ws.__messages.push(entry);
            window.__wsMessages.push(entry);
            return origSend(data);
        };
        
        ws.addEventListener('message', function(e) {
            const entry = {ts: Date.now(), dir: 'IN', url: ws.__url, data: null};
            try { entry.data = typeof e.data === 'string' ? e.data.slice(0, 2000) : '[binary]'; } catch(err) {}
            ws.__messages.push(entry);
            window.__wsMessages.push(entry);
        });
        
        // Expose method to get and clear messages
        ws.__getMessages = function() { return ws.__messages.splice(0); };
        
        return ws;
    };
    Object.assign(window.WebSocket, OrigWebSocket);
})();
</script>
"""

class WSHook:
    def request(self, flow):
        # Only intercept ai.yun.139.com - ignore SSO
        if 'ai.yun.139.com' not in flow.request.pretty_host:
            flow.ignore_connection = True
            return
        
        auth = flow.request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            entry = json.dumps({"auth": auth, "url": flow.request.pretty_url})
            with open(CAPTURE_FILE, "a") as f:
                f.write(entry + "\n")
        
        url = flow.request.pretty_url
        if "openclaw" in url.lower() or "mclaw" in url.lower():
            print(f"[REQ] {flow.request.method} {url[:200]}", flush=True)
    
    def response(self, flow):
        if 'ai.yun.139.com' not in flow.request.pretty_host:
            return
        
        try:
            body = flow.response.content.decode('utf-8', errors='replace')
            if 'openclaw' in body.lower() or 'wsUrl' in body:
                print(f"[RESP] {flow.request.pretty_url[:100]} -> {body[:500]}", flush=True)
        except:
            pass
        
        # Inject WS hook into cloudClaw HTML pages
        ct = flow.response.headers.get('content-type', '')
        if 'text/html' in ct and b'<head>' in flow.response.content:
            if 'cloudclaw' in flow.request.pretty_host or 'appmail' in flow.request.pretty_host:
                body = flow.response.content
                body = body.replace(b'</head>', INJECT_JS + b'</head>')
                flow.response.content = body
                flow.response.headers['content-length'] = str(len(body))

addons = [WSHook()]
