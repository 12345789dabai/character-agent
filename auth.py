"""
认证模块 — API Key 验证 + Token 管理
"""
import hashlib
import hmac
import json
import time
import requests
from pathlib import Path

from config import BASE_DIR

# Token 密钥（用于签名 JWT）
_SECRET_FILE = BASE_DIR / ".auth_secret"

def _get_secret() -> str:
    """获取或创建 token 签名密钥"""
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    import secrets
    secret = secrets.token_hex(32)
    _SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret

def generate_user_id(api_key: str) -> str:
    """根据 API Key 生成 user_id（SHA256 前16位）"""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]

def generate_token(user_id: str) -> str:
    """生成简单 token（HMAC-SHA256）"""
    secret = _get_secret()
    payload = f"{user_id}:{int(time.time())}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_token(token: str) -> str | None:
    """验证 token，返回 user_id 或 None"""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id, timestamp, signature = parts
        secret = _get_secret()
        payload = f"{user_id}:{timestamp}"
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        # Token 有效期 30 天
        if int(time.time()) - int(timestamp) > 30 * 24 * 3600:
            return None
        return user_id
    except (ValueError, IndexError):
        return None

def verify_api_key(provider: str, api_key: str, model: str = "",
                   base_url: str = "") -> tuple[bool, str]:
    """
    验证 API Key 是否有效
    返回 (是否有效, 错误信息)
    """
    if provider == "ollama":
        # Ollama 不需要 key，检查连接即可
        try:
            url = (base_url or "http://localhost:11434").rstrip("/")
            resp = requests.get(f"{url}/api/tags", timeout=5)
            resp.raise_for_status()
            return True, ""
        except Exception as e:
            return False, f"无法连接 Ollama: {e}"

    # OpenAI 兼容接口
    url = (base_url or "https://api.openai.com/v1").rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"

    try:
        # 尝试获取模型列表
        resp = requests.get(
            f"{url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, ""
        if resp.status_code == 401:
            return False, "API Key 无效"
        # 某些 API 不支持 /models，尝试发送简单请求
        resp = requests.post(
            f"{url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return True, ""
        if resp.status_code == 401:
            return False, "API Key 无效"
        # 其他错误可能只是模型不对，但 Key 是有效的
        return True, ""
    except requests.ConnectionError:
        return False, f"无法连接到 {base_url}"
    except requests.Timeout:
        return False, "连接超时"
    except Exception as e:
        return False, str(e)
