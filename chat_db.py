"""短期记忆持久化 — SQLite 存储对话历史（按角色隔离）"""

import sqlite3
from pathlib import Path


class ChatDB:
    def __init__(self, db_path: str, user_id: str = ""):
        if user_id:
            # 多用户模式：数据存到 user_data/{user_id}/chat_history.db
            db_file = Path(db_path) / "user_data" / user_id / "chat_history.db"
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(db_file), check_same_thread=False)
        else:
            # 单用户模式（兼容旧数据）
            self.conn = sqlite3.connect(db_path, check_same_thread=False)

        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  role TEXT NOT NULL,"
            "  content TEXT NOT NULL,"
            "  character TEXT NOT NULL DEFAULT '',"
            "  created_at TEXT DEFAULT (datetime('now','localtime'))"
            ")"
        )
        # 迁移：给旧数据加 character 列
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN character TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()
        self._migrate_empty_characters()
        self._current_char = ""

    def _migrate_empty_characters(self):
        """迁移旧数据：把 character='' 的消息归到 'default'，后续查询不再兼容空值"""
        self.conn.execute("UPDATE messages SET character='default' WHERE character=''")
        self.conn.commit()

    @property
    def current_char(self) -> str:
        return self._current_char

    @current_char.setter
    def current_char(self, name: str):
        self._current_char = name

    def add(self, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (role, content, character) VALUES (?, ?, ?)",
            (role, content, self._current_char),
        )
        self.conn.commit()

    def get_all(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT role, content FROM messages WHERE character=? ORDER BY id ASC",
            (self._current_char,),
        )
        return [{"role": r[0], "content": r[1]} for r in cur.fetchall()]

    def get_last_n(self, n: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT role, content FROM messages WHERE character=? ORDER BY id DESC LIMIT ?",
            (self._current_char, n),
        )
        rows = cur.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def count(self) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE character=?", (self._current_char,)
        )
        return cur.fetchone()[0]

    def last_message_time(self) -> str | None:
        cur = self.conn.execute(
            "SELECT created_at FROM messages WHERE character=? ORDER BY id DESC LIMIT 1",
            (self._current_char,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def clear(self):
        self.conn.execute(
            "DELETE FROM messages WHERE character=?", (self._current_char,)
        )
        self.conn.commit()
