import sys
from pathlib import Path

# 打包后数据文件在 sys._MEIPASS，用户数据在 exe 所在位置
if getattr(sys, 'frozen', False):
    DATA_DIR = Path(sys._MEIPASS)   # 打包的资源文件（static, characters）
    BASE_DIR = Path(sys.executable).parent  # 用户数据（配置，数据库）
else:
    DATA_DIR = Path(__file__).parent
    BASE_DIR = DATA_DIR

CHARACTERS_DIR = DATA_DIR / "characters"
MEMORY_DIR = str(BASE_DIR / "memory_db")

# 用户数据目录（多用户模式）
USER_DATA_DIR = BASE_DIR / "user_data"

# ---------- LLM 配置 ----------
# 可选 "ollama"（免费本地）或 "openai"（需 API Key）
LLM_PROVIDER = "ollama"

# Ollama 设置
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5"  # 中文好，推荐。轻量可选 qwen2.5:3b

# OpenAI 设置（使用 LLM_PROVIDER="openai" 时生效）
OPENAI_API_KEY = ""       # 或从环境变量读取
OPENAI_MODEL = "gpt-4o-mini"

# ---------- 记忆配置 ----------
MAX_HISTORY_TURNS = 10          # 短期记忆保留最近 N 轮

# 记忆层级与过期天数（角色时间）
MEMORY_LAYERS = {
    "L0": {"label": "核心信念", "expire_days": None,    "weight_base": 3.0},  # 永不过期
    "L1": {"label": "重要事实", "expire_days": 180,      "weight_base": 1.5},  # ~半年
    "L2": {"label": "一般经历", "expire_days": 30,       "weight_base": 0.8},  # ~1个月
    "L3": {"label": "日常琐事", "expire_days": 3,        "weight_base": 0.3},  # ~3天
}

# 权重倍率
WEIGHT_SELF = 3.0      # 角色自己说的内容
WEIGHT_USER = 1.0      # 用户说的关于角色的内容
WEIGHT_CHAT = 0.5      # 普通闲聊

# 重复升级：同一内容出现 N 次自动升级到上一级
REPEAT_UPGRADE_THRESHOLD = 3

# ---------- 生命周期配置 ----------
LIFECYCLE = {
    # 时间推进
    "TIME_PER_MESSAGE": 10,              # 连续聊天每条消息推进（分钟）
    "TIME_FAST_REPLY_MINUTES": 1,        # 快速回复（<2分钟间隔）推进
    "TIME_NORMAL_REPLY_MINUTES": 10,     # 正常回复（2-30分钟间隔）推进
    "TIME_GAP_MULTIPLIER": 2,            # 大间隔聊天倍率
    "OFFLINE_HOUR_TO_DAY": 1,            # 离线每1小时=角色1天
    "OFFLINE_TRIGGER_DAYS": 3,           # 离线超过多少天触发离线经历生成

    # 阶段制 — 梯度阈值（每个阶段需要的消息数）
    "STAGES": ["相遇", "相伴", "成长", "沉淀", "告别"],
    "STAGE_THRESHOLDS": [100, 300, 300, 400, 500],

    # 各阶段的语气描述（注入 prompt 用）
    "STAGE_PROMPTS": {
        "相遇": "你和对方认识不久，还有点陌生。你有些腼腆但努力想给对方留下好印象，说话会有点小心，偶尔害羞。",
        "相伴": "你和对方已经熟悉起来了。你感到轻松自然，偶尔会开玩笑，像真正的朋友一样相处。",
        "成长": "你们一起经历了不少事。你开始更坦率地表达自己的想法，也愿意倾听对方的深入话题。",
        "沉淀": "你变得成熟稳重了许多。你开始回想和对方一起走过的路，觉得每一段对话都值得珍惜。",
        "告别": "你深刻意识到这段旅程快要结束了。你变得更真诚、更坦率，想把最真实的自己留给对方。",
    },
}
