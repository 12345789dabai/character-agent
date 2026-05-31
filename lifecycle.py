"""
生命周期管理：时间推进、阶段计算、离线经历
"""
from datetime import datetime
from config import LIFECYCLE


class LifecycleManager:
    def __init__(self, data: dict):
        self.data = data

    # ── 配置读写 ──

    def get_lc(self) -> dict:
        return self.data.setdefault("生命周期", {
            "阶段": 0,
            "阶段名": "相遇",
            "消息计数": 0,
            "总消息数": 0,
            "固定结局": False,
            "已知结局描述": "",
            "最后活跃": None,
            "离线经历生成时间": None,
        })

    # ── 时间推进 ──

    def advance(self, offline_hours: float = 0, gap_seconds: float = 0):
        """
        推进角色时间。返回 (当前阶段索引, 阶段名, 是否进入新阶段)
        """
        lc = self.get_lc()
        stages = LIFECYCLE["STAGES"]
        thresholds = LIFECYCLE["STAGE_THRESHOLDS"]

        # 确定推进多少分钟
        if offline_hours > 0:
            advance_minutes = offline_hours * 60 * LIFECYCLE["OFFLINE_HOUR_TO_DAY"]
        elif gap_seconds < 120:
            advance_minutes = LIFECYCLE["TIME_FAST_REPLY_MINUTES"]
        elif gap_seconds < 1800:
            advance_minutes = LIFECYCLE["TIME_NORMAL_REPLY_MINUTES"]
        else:
            advance_minutes = (gap_seconds / 60) * LIFECYCLE["TIME_GAP_MULTIPLIER"]

        lc["消息计数"] = lc.get("消息计数", 0) + 1
        lc["总消息数"] = lc.get("总消息数", 0) + 1
        lc["最后活跃"] = datetime.now().isoformat()

        # 阶段推进：梯度阈值，每个阶段需要不同的消息数
        old_stage = lc.get("阶段", 0)
        msg_count = lc.get("消息计数", 0)
        safe_idx = min(old_stage, len(thresholds) - 1)
        threshold = thresholds[safe_idx]

        if msg_count >= threshold and old_stage < len(stages) - 1:
            lc["阶段"] = old_stage + 1
            lc["消息计数"] = 0
            lc["阶段名"] = stages[lc["阶段"]]
            return (lc["阶段"], lc["阶段名"], True)

        lc["阶段名"] = stages[old_stage]
        return (old_stage, lc["阶段名"], False)

    # ── 结局检查 ──

    def check_ending(self) -> dict:
        """检查是否到达结局。返回 {ending: bool, type: str, description: str}"""
        lc = self.get_lc()
        stages = LIFECYCLE["STAGES"]
        current_stage = lc.get("阶段", 0)

        # 固定结局
        if lc.get("固定结局") and lc.get("已知结局描述"):
            if current_stage >= len(stages) - 1:
                return {
                    "ending": True,
                    "type": "fixed",
                    "description": lc.get("已知结局描述", ""),
                    "stage": current_stage,
                }

        # 开放结局：走完所有阶段
        if current_stage >= len(stages):
            return {
                "ending": True,
                "type": "natural",
                "description": "走完了人生的旅程",
                "stage": current_stage,
            }

        return {"ending": False}

    # ── 离线经历 ──

    def should_generate_offline_life(self) -> bool:
        """判断是否需要生成离线经历"""
        lc = self.get_lc()
        last_active = lc.get("最后活跃")
        if not last_active:
            return False
        last_gen = lc.get("离线经历生成时间")
        if last_gen:
            # 一天内不重复生成
            try:
                if (datetime.now() - datetime.fromisoformat(last_gen)).days < 1:
                    return False
            except (ValueError, TypeError):
                pass
        try:
            days = (datetime.now() - datetime.fromisoformat(last_active)).days
            return days >= LIFECYCLE["OFFLINE_TRIGGER_DAYS"]
        except (ValueError, TypeError):
            return False

    def mark_offline_generated(self):
        lc = self.get_lc()
        lc["离线经历生成时间"] = datetime.now().isoformat()

    # ── 阶段提示词 ──

    def get_stage_prompt(self, char_name: str) -> str:
        """获取当前阶段的 prompt 注入文本"""
        lc = self.get_lc()
        stage = lc.get("阶段名", "相遇")
        prompts = LIFECYCLE.get("STAGE_PROMPTS", {})
        desc = prompts.get(stage, "")
        if not desc:
            return ""
        total = lc.get("总消息数", 0)
        return (
            f"\n【角色当前状态】\n"
            f"{char_name}目前处于人生的「{stage}」阶段。{desc}\n"
            f"你们已经聊了{total}轮对话。"
        )

    # ── 角色卡配置导入 ──

    def load_from_char_card(self, card: dict):
        """从角色卡读取生命周期配置"""
        lc_data = card.get("生命周期", {})
        lc = self.get_lc()
        lc["固定结局"] = lc_data.get("固定结局", False)
        lc["已知结局描述"] = lc_data.get("已知结局", "") or ""
        lc["阶段"] = 0
        lc["阶段名"] = LIFECYCLE["STAGES"][0]
        lc["消息计数"] = 0
