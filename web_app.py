"""
Web 服务器 — 后台任务 + 聊天界面 API
"""
import json
import os
from pathlib import Path
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import *
from character import Character
from memory import MemoryStore
from llm import LLM, LLMError

# ============================================================
# 全局状态
# ============================================================
active_char: Character | None = None
memory_store: MemoryStore | None = None
llm: LLM | None = None
chat_history: list[dict] = []
_settings: dict | None = None  # 当前生效的设置

SETTINGS_FILE = Path(__file__).parent / "user_settings.json"

app = FastAPI(title="永久角色对话 Agent")


# ============================================================
# 设置持久化
# ============================================================
def load_settings_from_file() -> dict | None:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_settings_to_file(s: dict):
    SETTINGS_FILE.write_text(
        json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def apply_settings(s: dict):
    """应用设置：创建新的 LLM 实例"""
    global llm, _settings
    _settings = s
    provider = s.get("provider", "openai")
    api_key = s.get("api_key", "")
    model = s.get("model", "gpt-4o-mini")
    base_url = s.get("base_url", "")

    # OpenAI 兼容 API 需要在环境变量里设 key
    if provider == "openai" and api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    llm = LLM(provider=provider, model=model, base_url=base_url, api_key=api_key)


# ============================================================
# 初始化
# ============================================================
@app.on_event("startup")
def startup():
    global active_char, memory_store
    # 加载角色
    chars = Character.list_available()
    if chars:
        active_char = chars[0][1]
        memory_store = MemoryStore(MEMORY_DIR, active_char.name)
        print(f"[就绪] 角色「{active_char.name}」| 记忆 {memory_store.count()} 条")
    else:
        print("[警告] characters/ 下没有角色卡")

    # 加载上次保存的设置
    saved = load_settings_from_file()
    if saved:
        try:
            apply_settings(saved)
            print(f"[设置] 已加载：{saved['provider']} / {saved['model']}")
        except Exception as e:
            print(f"[设置] 加载失败：{e}")

    print(f"[服务] http://127.0.0.1:8000")


# ============================================================
# 请求/响应模型
# ============================================================
class ChatRequest(BaseModel):
    message: str


class SettingsBody(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""


# ============================================================
# API 路由
# ============================================================
@app.get("/api/status")
def get_status():
    return {
        "configured": llm is not None,
        "character": active_char.name if active_char else None,
        "greeting": active_char.greeting if active_char else "",
        "memory_count": memory_store.count() if memory_store else 0,
    }


@app.get("/api/settings")
def get_settings():
    """返回当前设置（API Key 脱敏）"""
    if not _settings:
        return {"provider": "openai", "api_key": "", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"}
    s = dict(_settings)
    if s.get("api_key"):
        k = s["api_key"]
        s["api_key"] = k[:6] + "..." + k[-4:] if len(k) > 12 else "********"
    return s


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    """保存并应用设置"""
    s = {
        "provider": body.provider,
        "api_key": body.api_key,
        "model": body.model,
        "base_url": body.base_url.rstrip("/"),
    }

    # 验证必要字段
    if body.provider == "openai" and not body.api_key:
        raise HTTPException(400, "API Key 不能为空")

    try:
        apply_settings(s)
    except Exception as e:
        raise HTTPException(500, f"设置应用失败：{e}")

    save_settings_to_file(s)
    return {"ok": True, "message": f"已切换到 {s['provider']} / {s['model']}"}


@app.get("/api/characters")
def list_characters():
    return [
        {"name": c.name, "greeting": c.greeting, "relationship": c.relationship}
        for _, c in Character.list_available()
    ]


@app.post("/api/chat")
def chat(req: ChatRequest, background: BackgroundTasks):
    """发消息 → 查记忆 → LLM 回复 → 后台存记忆"""
    global chat_history

    if not llm:
        raise HTTPException(503, "请先在设置中配置 API")
    if not active_char or not memory_store:
        raise HTTPException(503, "系统尚未初始化（没有角色卡）")

    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 1. 检索相关长期记忆
    memories = memory_store.search(user_input, n_results=TOP_K_MEMORIES)

    # 2. 组装 prompt
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-(MAX_HISTORY_TURNS * 2):])
    messages.append({"role": "user", "content": user_input})

    # 3. 调用 LLM
    try:
        response = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(500, str(e))

    # 4. 更新短期记忆
    chat_history.append({"role": "user", "content": user_input})
    chat_history.append({"role": "assistant", "content": response})

    # 5. 后台提取并存储长期记忆
    background.add_task(_extract_memory_background, list(chat_history))

    return {
        "reply": response,
        "character_name": active_char.name,
        "memory_count": memory_store.count(),
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, background: BackgroundTasks):
    """流式版：发消息 → 查记忆 → LLM 逐字返回 → 后台存记忆"""
    if not llm:
        raise HTTPException(503, "请先在设置中配置 API")
    if not active_char or not memory_store:
        raise HTTPException(503, "系统尚未初始化（没有角色卡）")

    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 预检索（同步）
    memories = memory_store.search(user_input, n_results=TOP_K_MEMORIES)
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-(MAX_HISTORY_TURNS * 2):])
    messages.append({"role": "user", "content": user_input})

    def event_stream():
        full_response = ""
        try:
            for chunk in llm.chat_stream(messages):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except LLMError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # 流结束后更新短期记忆
        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "assistant", "content": full_response})

        # 后台提取长期记忆（每轮都尝试，但 LLM 会判断是否有价值）
        background.add_task(_extract_memory_background, list(chat_history))

        yield f"data: {json.dumps({'done': True, 'memory_count': memory_store.count(), 'character_name': active_char.name})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
def get_history():
    return chat_history[-MAX_HISTORY_TURNS * 2:]


@app.get("/api/memories")
def list_memories():
    if not memory_store:
        return []
    return memory_store.get_all(limit=100)


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    if not memory_store:
        raise HTTPException(503, "记忆系统未初始化")
    memory_store.delete_memory(memory_id)
    return {"ok": True}


# ============================================================
# 后台任务
# ============================================================
def _extract_memory_background(history_snapshot: list):
    """后台：取最后一轮对话 → 判断是否有价值 → 去重 → 存入"""
    # 只处理最后一轮（2 条记录）
    recent = history_snapshot[-2:] if len(history_snapshot) >= 2 else history_snapshot
    lines = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "角色"
        lines.append(f"{role}: {msg['content']}")
    history_text = "\n".join(lines)
    if not history_text.strip():
        return

    data = llm.extract_memory(history_text)
    if not data or not data.get("worth") or not data.get("summary"):
        return  # LLM 判断没有值得记的信息

    # 去重：检查是否已有相似记忆
    if memory_store.has_similar(data["summary"]):
        return

    memory_store.add_memory(
        summary=data["summary"],
        facts=data.get("facts", []),
        topics=data.get("topics", []),
    )


# ============================================================
# 静态文件
# ============================================================
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
