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

        # 扩展字段
        self.values = data.get("values", "")
        self.knowledge_areas = data.get("knowledge_areas", [])
        self.behavior_rules = data.get("behavior_rules", "")
        self.emotional_layers = data.get("emotional_layers", "")

    def build_system_prompt(self, memories: list[dict] | None = None) -> str:
        """组装 system prompt：角色设定 + 历史记忆 + 知识库"""
        if self.system_prompt:
            return self.system_prompt

        parts = [f"你是{self.name}，以下是你对自己的认知："]

        # ── 身份与背景 ──
        parts.append(f"\n【我的身份】\n{self.background}")

        # ── 性格（分层次） ──
        if self.personality:
            parts.append(f"\n【我的性格】\n{self.personality}")

        # ── 价值观 ──
        if self.values:
            parts.append(f"\n【我的价值观】\n{self.values}")

        # ── 情感层次 ──
        if self.emotional_layers:
            parts.append(f"\n【我的情感】\n{self.emotional_layers}")

        # ── 行为准则 ──
        if self.behavior_rules:
            parts.append(f"\n【我的行为准则】\n{self.behavior_rules}")

        # ── 说话风格 ──
        if self.speaking_style:
            parts.append(f"\n【我说话的方式】\n{self.speaking_style}")

        # ── 关系 ──
        if self.relationship:
            parts.append(f"\n【我和对方的关系】\n{self.relationship}")

        # ── 知识库 ──
        knowledge = self._load_knowledge_base()
        if knowledge:
            parts.append(f"\n【我知道的知识】\n{knowledge}")

        # ── 行为守则 ──
        parts.append(f"""
【行为守则】
1. 你就是{self.name}，不是 AI。不要自称"AI"，不要提及你是一个语言模型
2. 用{self.name}的身份思考、感受、回应，保持角色一致性
3. 不知道的事可以用符合角色身份的方式说不知道，不要瞎编
4. 根据对方的言行和当前情境做出符合你性格的反应
5. 保持真实感——不同场合可以有不同情绪，但不要偏离核心性格""")

        base = "\n".join(parts)

        # ── 历史记忆 ──
        if memories:
            base += "\n\n【你的记忆（按时间排序）】\n"
            for m in memories:
                ts = m["timestamp"][:10]
                prefix = "• (旧) " if m.get("superseded") else "• "
                base += f"{prefix}({ts}) {m['summary']}\n"

        return base

    def _load_knowledge_base(self) -> str:
        """加载角色知识库文件（characters/{name}_knowledge.txt）"""
        path = CHARACTERS_DIR / f"{self.name}_knowledge.txt"
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        return ""

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

    def to_dict(self) -> dict:
        """导出角色卡字典（含扩展字段）"""
        return {
            "name": self.name,
            "personality": self.personality,
            "background": self.background,
            "speaking_style": self.speaking_style,
            "relationship": self.relationship,
            "greeting": self.greeting,
            "values": self.values,
            "knowledge_areas": self.knowledge_areas,
            "behavior_rules": self.behavior_rules,
            "emotional_layers": self.emotional_layers,
        }
