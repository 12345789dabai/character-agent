import json
from pathlib import Path
from config import CHARACTERS_DIR


class Character:
    def __init__(self, data: dict):
        self.name = data.get("name", "助手")
        self.personality = data.get("personality", "")
        self.background = data.get("background", "")
        self.speaking_style = data.get("speaking_style", "")
        self.relationship = data.get("relationship_to_user", "")
        self.greeting = data.get("greeting", "你好！开始聊天吧。")
        self.system_prompt = data.get("system_prompt", "")

    def build_system_prompt(self, memories: list[dict] | None = None) -> str:
        """组装 system prompt：角色设定 + 历史记忆"""
        if self.system_prompt:
            base = self.system_prompt
        else:
            base = (
                f"你是{self.name}。以下是你的角色设定：\n\n"
                f"性格：{self.personality}\n"
                f"背景：{self.background}\n"
                f"说话风格：{self.speaking_style}\n"
                f"和用户的关系：{self.relationship}\n\n"
                f"请完全以{self.name}的身份和用户对话，不要跳出角色。"
            )

        if memories:
            base += "\n\n【你的历史记忆（按时间排序）】\n"
            for m in memories:
                ts = m["timestamp"][:10]
                prefix = "• (旧) " if m.get("superseded") else "• "
                base += f"{prefix}({ts}) {m['summary']}\n"

        return base

    @classmethod
    def load(cls, path: Path):
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    @classmethod
    def list_available(cls) -> list[tuple[Path, "Character"]]:
        """扫描 characters/ 目录，返回所有可用的角色"""
        results = []
        if not CHARACTERS_DIR.exists():
            return results
        for f in sorted(CHARACTERS_DIR.glob("*.json")):
            try:
                char = cls.load(f)
                results.append((f, char))
            except (json.JSONDecodeError, KeyError):
                continue
        return results
