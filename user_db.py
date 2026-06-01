"""
用户数据库管理 — SQLite 存储用户信息
"""
import sqlite3
from pathlib import Path
from datetime import datetime

from config import BASE_DIR

USER_DB_PATH = str(BASE_DIR / "users.db")


class UserDB:
    def __init__(self, db_path: str = USER_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    api_key_encrypted TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'openai',
                    model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
                    base_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_login TEXT NOT NULL
                )
            """)
            conn.commit()

    def create_or_update(self, user_id: str, api_key_encrypted: str,
                         provider: str = "openai", model: str = "gpt-4o-mini",
                         base_url: str = "") -> dict:
        """创建或更新用户"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE users
                    SET api_key_encrypted = ?, provider = ?, model = ?,
                        base_url = ?, last_login = ?
                    WHERE user_id = ?
                """, (api_key_encrypted, provider, model, base_url, now, user_id))
            else:
                conn.execute("""
                    INSERT INTO users (user_id, api_key_encrypted, provider,
                                      model, base_url, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, api_key_encrypted, provider, model, base_url, now, now))
            conn.commit()

        return {
            "user_id": user_id,
            "provider": provider,
            "model": model,
            "base_url": base_url,
        }

    def get_user(self, user_id: str) -> dict | None:
        """获取用户信息"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict]:
        """列出所有用户（管理用）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT user_id, provider, model, created_at, last_login FROM users"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM users WHERE user_id = ?", (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
