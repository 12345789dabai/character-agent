"""短期记忆持久化 — SQLite 存储对话历史"""

import sqlite3
from datetime import datetime
from pathlib import Path


class ChatDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  role TEXT NOT NULL,"
            "  content TEXT NOT NULL,"
            "  created_at TEXT DEFAULT (datetime('now','localtime'))"
            ")"
        )
        self.conn.commit()

    def add(self, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content),
        )
        self.conn.commit()

    def get_all(self) -> list[dict]:
        """按时间正序返回全部对话"""
        cur = self.conn.execute(
            "SELECT role, content FROM messages ORDER BY id ASC"
        )
        return [{"role": r[0], "content": r[1]} for r in cur.fetchall()]

    def get_last_n(self, n: int) -> list[dict]:
        """取最近 N 条（用于注入 prompt）"""
        cur = self.conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = cur.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM messages")
        return cur.fetchone()[0]

    def turn_count(self) -> int:
        """对话轮数（每条消息算半轮）"""
        return self.count() // 2

    def last_message_time(self) -> str | None:
        """最后一条消息的时间"""
        cur = self.conn.execute(
            "SELECT created_at FROM messages ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row[0] if row else None

    def clear(self):
        self.conn.execute("DELETE FROM messages")
        self.conn.commit()
