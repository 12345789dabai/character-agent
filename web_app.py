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
from chat_db import ChatDB

# ============================================================
# 全局状态
# ============================================================
active_char: Character | None = None
memory_store: MemoryStore | None = None
chat_db: ChatDB | None = None
llm: LLM | None = None
_settings: dict | None = None

DB_DIR = Path(__file__).parent
SETTINGS_FILE = DB_DIR / "user_settings.json"
HISTORY_DB = str(DB_DIR / "chat_history.db")

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
    global llm, _settings
    _settings = s
    provider = s.get("provider", "openai")
    api_key = s.get("api_key", "")
    model = s.get("model", "gpt-4o-mini")
    base_url = s.get("base_url", "")

    if provider == "openai" and api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    llm = LLM(provider=provider, model=model, base_url=base_url, api_key=api_key)


# ============================================================
# 初始化
# ============================================================
@app.on_event("startup")
def startup():
    global active_char, memory_store, chat_db

    chat_db = ChatDB(HISTORY_DB)
    print(f"[就绪] 对话历史 {chat_db.count()} 条")

    chars = Character.list_available()
    if chars:
        active_char = chars[0][1]
        memory_store = MemoryStore(MEMORY_DIR, active_char.name)
        print(f"[就绪] 角色「{active_char.name}」| 记忆 {memory_store.count()} 条")
    else:
        print("[警告] characters/ 下没有角色卡")

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
        "history_count": chat_db.count() if chat_db else 0,
    }


@app.get("/api/settings")
def get_settings():
    if not _settings:
        return {"provider": "openai", "api_key": "", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"}
    s = dict(_settings)
    if s.get("api_key"):
        k = s["api_key"]
        s["api_key"] = k[:6] + "..." + k[-4:] if len(k) > 12 else "********"
    return s


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    s = {
        "provider": body.provider,
        "api_key": body.api_key,
        "model": body.model,
        "base_url": body.base_url.rstrip("/"),
    }

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
    """非流式版"""
    if not all([llm, active_char, memory_store, chat_db]):
        raise HTTPException(503, "系统未初始化")
    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    memories = memory_store.search(user_input, n_results=TOP_K_MEMORIES)
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_db.get_last_n(MAX_HISTORY_TURNS * 2))
    messages.append({"role": "user", "content": user_input})

    try:
        response = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(500, str(e))

    chat_db.add("user", user_input)
    chat_db.add("assistant", response)
    background.add_task(_extract_memory_background)

    return {
        "reply": response,
        "character_name": active_char.name,
        "memory_count": memory_store.count(),
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, background: BackgroundTasks):
    """流式版"""
    if not all([llm, active_char, memory_store, chat_db]):
        raise HTTPException(503, "系统未初始化")
    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    memories = memory_store.search(user_input, n_results=TOP_K_MEMORIES)
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_db.get_last_n(MAX_HISTORY_TURNS * 2))
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

        chat_db.add("user", user_input)
        chat_db.add("assistant", full_response)
        background.add_task(_extract_memory_background)

        yield f"data: {json.dumps({'done': True, 'memory_count': memory_store.count(), 'character_name': active_char.name})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
def get_history():
    if not chat_db:
        return []
    return chat_db.get_last_n(MAX_HISTORY_TURNS * 2)


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
def _extract_memory_background():
    """后台：取最后一轮对话 → 判断是否有价值 → 去重 → 存入"""
    recent = chat_db.get_last_n(2)
    if len(recent) < 2:
        return

    lines = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "角色"
        lines.append(f"{role}: {msg['content']}")
    history_text = "\n".join(lines)

    data = llm.extract_memory(history_text)
    if not data or not data.get("worth") or not data.get("summary"):
        return

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
