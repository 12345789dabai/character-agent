"""
层级记忆系统：L0-L3 + 情绪强度 + 热度衰减 + 情绪轨道
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from config import MEMORY_LAYERS, LIFECYCLE
from lifecycle import LifecycleManager

# 热度衰减系数：越低衰减越快
_DECAY_FACTOR = 0.97
# 热度阈值：低于此值不进入 prompt
_HEAT_THRESHOLD = 0.15
# 情绪轨道保留轮数
_MOOD_TRACK_SIZE = 8


class MemoryStore:
    def __init__(self, db_path: str, character_name: str):
        self.file = Path(db_path) / f"{character_name}_memory.json"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self._data = {"L0": [], "L1": [], "L2": [], "L3": [],
                       "日志": [], "情绪轨道": []}
        self._last_cleanup = None
        self._load()

    # ── 内部方法 ──

    def _load(self):
        if self.file.exists():
            try:
                self._data = json.loads(self.file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        self._ensure_ids()
        self._migrate()

    def get_lifecycle(self) -> LifecycleManager:
        """获取生命周期管理器"""
        return LifecycleManager(self._data)

    def _migrate(self):
        old_map = {"永久": "L0", "中期": "L1", "短期": "L2"}
        for old_key, new_key in old_map.items():
            if old_key in self._data:
                for m in self._data[old_key]:
                    m["level"] = new_key
                    m.setdefault("weight", 1.0)
                    m.setdefault("source", "chat")
                    m.setdefault("repeat_count", 0)
                    m.setdefault("emotion_intensity", 0.5)
                    m.setdefault("access_count", 0)
                    m.setdefault("last_accessed", None)
                    self._data.setdefault(new_key, []).append(m)
                del self._data[old_key]
        for layer in ["L0", "L1", "L2", "L3"]:
            self._data.setdefault(layer, [])
        self._data.setdefault("日志", [])
        self._data.setdefault("情绪轨道", [])
        # 给已有记忆补充新字段
        for layer in ["L0", "L1", "L2", "L3"]:
            for m in self._data.get(layer, []):
                m.setdefault("emotion_intensity", 0.5)
                m.setdefault("access_count", 0)
                m.setdefault("last_accessed", None)

    def _save(self):
        self.file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _ensure_ids(self):
        now = datetime.now()
        for items in self._data.values():
            if isinstance(items, list):
                for i, m in enumerate(items):
                    if "id" not in m:
                        m["id"] = f"mem_{now.strftime('%Y%m%d_%H%M%S_%f')}_{i}"

    def _make_id(self) -> str:
        return f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    def _heat_score(self, m: dict) -> float:
        """
        热度 = 有效权重 × 时间衰减 × 访问增益
        - 有效权重 = base_weight × (1 + 0.3 × repeat)
        - 时间衰减 = 0.97 ^ 距离上次的天数
        - 访问增益 = 1 + 0.1 × access_count
        """
        base = m.get("weight", 1.0)
        repeat = m.get("repeat_count", 0)
        emotion = m.get("emotion_intensity", 0.0)
        effective = base * (1.0 + 0.3 * repeat) * (1.0 + emotion * 0.8)

        last_str = m.get("last_accessed") or m.get("created")
        days = 0
        if last_str:
            try:
                last = datetime.fromisoformat(last_str)
                days = (datetime.now() - last).total_seconds() / 86400
            except (ValueError, TypeError):
                days = 0

        decay = _DECAY_FACTOR ** max(days, 0)
        access_boost = 1.0 + 0.1 * m.get("access_count", 0)

        return effective * decay * access_boost

    def _mark_accessed(self, m: dict):
        """标记记忆被访问：更新 last_accessed 和 access_count"""
        m["last_accessed"] = datetime.now().isoformat()
        m["access_count"] = m.get("access_count", 0) + 1

    # ── 对外接口 ──

    def get_active(self) -> list[dict]:
        """
        获取活跃记忆：L0 全部返回，L1-L3 按热度筛选
        每访问一次会更新 last_accessed
        """
        result = []
        for layer in ["L0", "L1", "L2", "L3"]:
            for m in self._data.get(layer, []):
                if layer == "L0":
                    # L0 核心信念始终返回
                    m["_heat"] = self._heat_score(m)
                    self._mark_accessed(m)
                    result.append(m)
                else:
                    heat = self._heat_score(m)
                    if heat >= _HEAT_THRESHOLD:
                        m["_heat"] = heat
                        self._mark_accessed(m)
                        result.append(m)

        result.sort(key=lambda x: (-x["_heat"], x.get("created", "")))
        for m in result:
            m.pop("_heat", None)
        self._save()
        return result

    def add(self, content: str, level: str, weight: float = 1.0,
            source: str = "chat", repeat_count: int = 0,
            emotion_intensity: float = 0.5):
        now = datetime.now()
        layer_cfg = MEMORY_LAYERS.get(level, {})
        entry = {
            "id": self._make_id(),
            "content": content.strip(),
            "level": level,
            "weight": weight,
            "source": source,
            "repeat_count": repeat_count,
            "emotion_intensity": emotion_intensity,
            "access_count": 1,
            "last_accessed": now.isoformat(),
            "created": now.isoformat(),
        }
        expire_days = layer_cfg.get("expire_days")
        if expire_days:
            entry["expires"] = (now + timedelta(days=expire_days)).isoformat()

        self._data.setdefault(level, []).append(entry)
        self._save()
        return entry["id"]

    def check_and_upgrade(self, content: str, level: str,
                          emotion_intensity: float = 0.5) -> dict:
        content_norm = content.strip().lower()
        layer_order = ["L3", "L2", "L1", "L0"]

        for layer in layer_order:
            for m in self._data.get(layer, []):
                if m.get("content", "").strip().lower() == content_norm:
                    m["repeat_count"] = m.get("repeat_count", 0) + 1
                    m["emotion_intensity"] = max(
                        m.get("emotion_intensity", 0.5), emotion_intensity
                    )
                    if m["repeat_count"] >= 3:
                        idx = layer_order.index(layer)
                        if idx > 0:
                            new_level = layer_order[idx - 1]
                            m["level"] = new_level
                            m["repeat_count"] = 0
                        self._save()
                        return {"action": "upgrade", "level": m["level"], "id": m["id"]}
                    self._save()
                    return {"action": "duplicate", "level": layer, "id": m["id"]}

        mid = self.add(content, level, emotion_intensity=emotion_intensity)
        return {"action": "add", "level": level, "id": mid}

    def add_mood(self, label: str, intensity: float):
        """添加情绪记录到情绪轨道"""
        self._data.setdefault("情绪轨道", []).append({
            "time": datetime.now().isoformat(),
            "label": label,
            "intensity": intensity,
        })
        # 只保留最近 N 条
        if len(self._data["情绪轨道"]) > _MOOD_TRACK_SIZE:
            self._data["情绪轨道"] = self._data["情绪轨道"][-_MOOD_TRACK_SIZE:]
        self._save()

    def get_mood_trend(self) -> str:
        """获取情绪趋势描述"""
        track = self._data.get("情绪轨道", [])
        if len(track) < 2:
            return ""
        avg = sum(e.get("intensity", 0.5) for e in track) / len(track)
        labels = list(set(e.get("label", "") for e in track if e.get("label")))
        if avg > 0.65:
            return f"当前情绪：较积极（{','.join(labels[:2])}）" if labels else "当前情绪：较好"
        elif avg < 0.35:
            return f"当前情绪：较低落（{','.join(labels[:2])}）" if labels else "当前情绪：不太好"
        return ""

    def add_log(self, text: str):
        self._data.setdefault("日志", []).append({
            "time": datetime.now().isoformat(),
            "content": text.strip(),
        })
        self._save()

    def search_log(self, keyword: str) -> list[dict]:
        kw = keyword.lower()
        result = []
        for entry in self._data.get("日志", []):
            if kw in entry.get("content", "").lower():
                result.append(entry)
        return result[-10:]

    def get_all(self) -> dict:
        for l in ["L0", "L1", "L2", "L3"]:
            self._data.setdefault(l, [])
        self._data.setdefault("日志", [])
        self._data.setdefault("情绪轨道", [])
        return self._data

    def update(self, memory_id: str, content: str):
        for items in self._data.values():
            if isinstance(items, list):
                for m in items:
                    if m.get("id") == memory_id:
                        m["content"] = content.strip()
                        self._save()
                        return True
        return False

    def delete(self, memory_id: str) -> bool:
        for items in self._data.values():
            if isinstance(items, list):
                for i, m in enumerate(items):
                    if m.get("id") == memory_id:
                        items.pop(i)
                        self._save()
                        return True
        return False

    def count(self) -> int:
        now = datetime.now()
        total = 0
        for layer in ["L0", "L1", "L2", "L3"]:
            for m in self._data.get(layer, []):
                if layer == "L0":
                    total += 1
                else:
                    expires = m.get("expires")
                    if not expires:
                        total += 1
                    else:
                        try:
                            if now <= datetime.fromisoformat(expires):
                                total += 1
                        except (ValueError, TypeError):
                            total += 1
        return total

    def format_for_prompt(self) -> str:
        """格式化记忆用于注入 system prompt"""
        active = self.get_active()
        if not active:
            return ""

        core = [m for m in active if m.get("level") == "L0"]
        other = [m for m in active if m.get("level") != "L0"]
        mood = self.get_mood_trend()

        lines = []
        if mood:
            lines.append(f"【情绪感知】{mood}")
            lines.append("")

        if core:
            lines.append("【我深信的事】")
            for m in core:
                lines.append(f"  • {m['content']}")
            lines.append("")

        if other:
            lines.append("【我记得的事】")
            for m in other:
                ts = m.get("created", "")[:10]
                prefix = f"({ts}) " if ts else ""
                source_tag = "(自己说的)" if m.get("source") == "self" else ""
                lines.append(f"  • {prefix}{m['content']} {source_tag}".strip())
            lines.append("")

        return "\n".join(lines)
