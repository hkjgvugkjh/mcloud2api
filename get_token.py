#!/usr/bin/env python3
"""
获取当前 mcloud 登录状态中的 authToken
"""
import json
import os
import base64

CONFIG_PATH = os.path.expanduser("~/.config/mcloud/config.json")
USERINFO_PATH = os.path.expanduser("~/.config/mcloud/userInfo.json")

def find_token():
    """从 mcloud 配置文件中查找 token"""
    
    # 尝试从 localStorage 恢复（如果存在）
    for path in [CONFIG_PATH, USERINFO_PATH]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                print(f"Found config at {path}:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                return data
            except:
                pass
    
    # 尝试从浏览器数据路径查找
    chrome_path = os.path.expanduser("~/.config/mcloud/Default/Local Storage/")
    if os.path.exists(chrome_path):
        for f in os.listdir(chrome_path):
            if "localstorage" in f.lower():
                full = os.path.join(chrome_path, f)
                try:
                    with open(full, 'rb') as fh:
                        content = fh.read()
                        # 寻找 authToken
                        idx = content.find(b'authToken')
                        if idx >= 0:
                            # 提取周围文本
                            start = max(0, idx - 10)
                            end = min(len(content), idx + 200)
                            print(f"Found authToken in {f}:")
                            print(content[start:end])
                except:
                    pass
    
    print("No token found in config files")
    return None

if __name__ == "__main__":
    find_token()
