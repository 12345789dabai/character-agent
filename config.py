from pathlib import Path

BASE_DIR = Path(__file__).parent
CHARACTERS_DIR = BASE_DIR / "characters"
MEMORY_DIR = str(BASE_DIR / "memory_db")

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
MAX_HISTORY_TURNS = 10        # 短期记忆保留最近 N 轮
TOP_K_MEMORIES = 3            # 每次对话检索几条相关记忆
SIMILARITY_THRESHOLD = 0.6    # 记忆检索距离阈值，大于此值的不注入 prompt
