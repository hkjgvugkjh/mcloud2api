#!/usr/bin/env python3
"""
mcloud2api - Token 管理模块

Token 格式: Basic base64("pc:{phone}:{authToken}")
刷新接口: POST https://user-njs.yun.139.com/user/auth/refreshToken
有效期: 30 天 (2592000 秒)

Token 来源:
1. ~/.config/mcloud/Local Storage/leveldb (UserInfo)
2. token.json 缓存文件
"""
import json
import time
import os
import base64
import re
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置
BASE_URL = "https://user-njs.yun.139.com"
TOKEN_FILE = os.path.expanduser("~/.hermes/workspace/mcloud2api/token.json")
MCLOUD_DB = os.path.expanduser("~/.config/mcloud/Local Storage/leveldb")


class TokenManager:
    """管理 mcloud 的 authToken"""

    def __init__(self, token_file=None):
        self.token_file = token_file or TOKEN_FILE
        self.token = None
        self.phone = None
        self.auth_token = None
        self.expire_time = 0

    def load_from_leveldb(self):
        """从 mcloud LevelDB 读取 token"""
        try:
            import plyvel
            db = plyvel.DB(MCLOUD_DB, create_if_missing=False)
            for key, value in db:
                key_str = key.decode('utf-8', errors='replace')
                if 'UserInfo' in key_str:
                    val_str = value.decode('utf-8', errors='replace')
                    # Remove leading \u0001
                    if val_str.startswith('\u0001'):
                        val_str = val_str[1:]
                    data = json.loads(val_str)
                    self.phone = data.get('account')
                    self.auth_token = data.get('authToken', data.get('token'))
                    self.token = self.auth_token
                    self.user_domain_id = data.get('userDomainId')
                    self.cutover_status = data.get('cutoverStatus')
                    db.close()
                    return True
            db.close()
        except Exception as e:
            print(f"LevelDB read error: {e}")
        return False

    def load(self):
        """从文件加载 token"""
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
        """保存 token 到文件"""
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
        """获取 Basic 认证头"""
        if not self.auth_token or not self.phone:
            return None
        return "Basic " + base64.b64encode(
            f"pc:{self.phone}:{self.auth_token}".encode()
        ).decode()

    def set_token(self, phone, auth_token, expire_seconds=2592000):
        """设置 token"""
        self.phone = phone
        self.auth_token = auth_token
        self.token = auth_token
        self.expire_time = time.time() + expire_seconds
        self.save()

    def is_expired(self):
        """检查 token 是否过期（提前 1 小时刷新）"""
        return time.time() >= (self.expire_time - 3600)

    def refresh(self):
        """刷新 token"""
        if not self.auth_token:
            if not self.load_from_leveldb():
                if not self.load():
                    return False

        if not self.is_expired():
            return True

        # 调用刷新接口
        auth = self.get_basic_auth()
        if not auth:
            return False

        try:
            resp = requests.post(
                f"{BASE_URL}/user/auth/refreshToken",
                json={"token": self.auth_token},
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "x-yun-app-channel": "522004",
                },
                verify=False,
                timeout=30,
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
        """确保 token 有效，先从 LevelDB 读取，过期则刷新"""
        # 首先尝试从 LevelDB 读取最新 token
        if self.load_from_leveldb():
            self.save()
        
        if self.is_expired():
            return self.refresh()
        return True


if __name__ == "__main__":
    # 测试
    mgr = TokenManager()
    if mgr.ensure_valid():
        print(f"Phone: {mgr.phone}")
        print(f"Token: {mgr.auth_token[:50]}...")
        print(f"Expired: {mgr.is_expired()}")
        print(f"Auth: {mgr.get_basic_auth()[:50]}...")
    else:
        print("No token loaded")
