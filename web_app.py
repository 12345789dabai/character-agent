"""
Web 服务器 — 后台任务 + 聊天界面 API
"""
import hashlib
import json
import re
import threading
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import *
from character import Character
from memory import MemoryStore
from llm import LLM, LLMError
from chat_db import ChatDB
from character_generator import generate_character as pipeline_generate

# ============================================================
# 全局状态
# ============================================================
active_char: Character | None = None
memory_store: MemoryStore | None = None
chat_db: ChatDB | None = None
llm: LLM | None = None
_settings: dict | None = None

SETTINGS_FILE = BASE_DIR / "user_settings.json"
HISTORY_DB = str(BASE_DIR / "chat_history.db")

# 后台任务锁：同一时刻只有一个记忆提取任务在执行
_memory_lock = threading.Lock()

# 访问密码
ACCESS_PASSWORD = "20041209"
ACCESS_HASH = hashlib.sha256(ACCESS_PASSWORD.encode()).hexdigest()

app = FastAPI(title="永久角色对话 Agent")


# ============================================================
# 访问密码中间件
# ============================================================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 放行登录相关路由
    if request.url.path == "/api/login":
        return await call_next(request)
    # 检查 API 路由
    if request.url.path.startswith("/api/"):
        token = request.cookies.get("auth_token")
        if not token or token != ACCESS_HASH:
            return JSONResponse(status_code=401, content={"detail": "需要访问密码"})
    return await call_next(request)


@app.post("/api/login")
def login(body: dict):
    pwd = body.get("password", "")
    if pwd == ACCESS_PASSWORD:
        resp = JSONResponse({"ok": True})
        resp.set_cookie(key="auth_token", value=ACCESS_HASH, httponly=True, max_age=86400 * 7, path="/")
        return resp
    raise HTTPException(401, "密码错误")


@app.get("/api/check-auth")
def check_auth(request: Request):
    token = request.cookies.get("auth_token")
    if not token or token != ACCESS_HASH:
        raise HTTPException(401, "需要访问密码")
    return {"ok": True}


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

    llm = LLM(provider=provider, model=model, base_url=base_url, api_key=api_key)


# ============================================================
# 初始化
# ============================================================
@app.on_event("startup")
def startup():
    global active_char, memory_store, chat_db

    chat_db = ChatDB(HISTORY_DB)
    print(f"[就绪] 对话历史 {chat_db.count()} 条")

    # 先加载设置，再创建记忆存储（支持 API 嵌入）
    saved = load_settings_from_file()
    if saved:
        try:
            apply_settings(saved)
            print(f"[设置] 已加载：{saved['provider']} / {saved['model']}")
        except Exception as e:
            print(f"[设置] 加载失败：{e}")

    chars = Character.list_available()
    if chars:
        active_char = chars[0][1]
        chat_db.current_char = active_char.name
        try:
            memory_store = MemoryStore(MEMORY_DIR, active_char.name, api_config=_settings)
            mem_count = memory_store.count()
            print(f"[就绪] 角色「{active_char.name}」| 记忆 {mem_count} 条 | 历史 {chat_db.count()} 条 | 嵌入:API")
        except (ValueError, Exception) as e:
            memory_store = None
            print(f"[就绪] 角色「{active_char.name}」| 记忆未加载（请先在设置中配置 API）: {e}")
    else:
        print("[警告] characters/ 下没有角色卡")

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


class CharacterSwitchBody(BaseModel):
    name: str


class CreateCharacterBody(BaseModel):
    name: str
    personality: str = ""
    background: str = ""
    speaking_style: str = ""
    relationship: str = ""
    greeting: str = ""
    values: str = ""
    knowledge_areas: list[str] = []
    behavior_rules: str = ""
    emotional_layers: str = ""


class GenerateCharacterBody(BaseModel):
    description: str


class UpdateCharacterBody(BaseModel):
    name: str
    new_name: str = ""
    personality: str = ""
    background: str = ""
    speaking_style: str = ""
    relationship: str = ""
    greeting: str = ""
    values: str = ""
    knowledge_areas: list[str] = []
    behavior_rules: str = ""
    emotional_layers: str = ""


class UpdateMemoryBody(BaseModel):
    summary: str = ""
    facts: list[str] = []
    topics: list[str] = []


class AddMemoryBody(BaseModel):
    summary: str
    facts: list[str] = []
    topics: list[str] = []


# ============================================================
# API 路由
# ============================================================
@app.get("/api/status")
def get_status():
    last_time = chat_db.last_message_time() if chat_db else None
    return {
        "configured": llm is not None,
        "character": active_char.name if active_char else None,
        "greeting": active_char.greeting if active_char else "",
        "memory_count": memory_store.count() if memory_store else 0,
        "history_count": chat_db.count() if chat_db else 0,
        "last_message_time": last_time,
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


@app.post("/api/settings/test")
def test_settings(body: SettingsBody):
    """测试 API 连接是否正常"""
    test_key = body.api_key or _settings.get("api_key", "") if _settings else ""
    test_model = body.model or _settings.get("model", "gpt-4o-mini") if _settings else "gpt-4o-mini"
    test_url = body.base_url or _settings.get("base_url", "") if _settings else ""
    test_provider = body.provider or _settings.get("provider", "openai") if _settings else "openai"

    if not test_key and test_provider == "openai":
        raise HTTPException(400, "请先输入 API Key")

    test_llm = LLM(provider=test_provider, model=test_model, base_url=test_url, api_key=test_key)
    try:
        resp = test_llm.chat([{"role": "user", "content": "回复 OK 即可"}])
        return {"ok": True, "message": "连接成功"}
    except LLMError as e:
        raise HTTPException(400, f"连接失败：{str(e)}")
    except Exception as e:
        raise HTTPException(400, f"连接失败：{str(e)}")


@app.get("/api/characters")
def list_characters():
    return [
        {"name": c.name, "greeting": c.greeting, "relationship": c.relationship}
        for _, c in Character.list_available()
    ]


@app.post("/api/character/switch")
def switch_character(body: CharacterSwitchBody):
    """切换角色（保留各自的对话历史）"""
    global active_char, memory_store
    for path, char in Character.list_available():
        if char.name == body.name:
            active_char = char
            chat_db.current_char = char.name
            try:
                memory_store = MemoryStore(MEMORY_DIR, char.name, api_config=_settings)
                mem_count = memory_store.count()
            except (ValueError, Exception):
                memory_store = None
                mem_count = 0
            return {
                "ok": True,
                "character": char.name,
                "greeting": char.greeting,
                "memory_count": mem_count,
                "history_count": chat_db.count(),
            }
    raise HTTPException(404, f"角色「{body.name}」不存在")


@app.post("/api/character/create")
def create_character(body: CreateCharacterBody):
    """创建新角色卡"""
    if not body.name.strip():
        raise HTTPException(400, "角色名不能为空")
    import re
    safe = re.sub(r'[\\/:*?"<>|]', '', body.name.strip())
    if not safe:
        raise HTTPException(400, "角色名包含非法字符")
    char_file = CHARACTERS_DIR / f"{safe}.json"
    if char_file.exists():
        raise HTTPException(400, f"角色「{safe}」已存在")
    data = {
        "name": safe,
        "personality": body.personality,
        "background": body.background,
        "speaking_style": body.speaking_style,
        "relationship_to_user": body.relationship,
        "greeting": body.greeting or f"你好！我是{safe}，很高兴认识你～",
        "values": body.values,
        "knowledge_areas": body.knowledge_areas,
        "behavior_rules": body.behavior_rules,
        "emotional_layers": body.emotional_layers,
    }
    char_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True, "name": safe}



@app.post("/api/character/generate")
def generate_character(body: GenerateCharacterBody):
    """AI 四阶段生成角色卡（搜索 → 分析 → 生成 → 知识库）"""
    if not body.description.strip():
        raise HTTPException(400, "描述不能为空")
    if not llm:
        raise HTTPException(503, "请先在设置中配置 API")

    try:
        result = pipeline_generate(body.description, llm)
        card = result["card"]
        knowledge_base = result["knowledge_base"]

        # 保存知识库文件
        if knowledge_base and card.get("name"):
            kb_path = CHARACTERS_DIR / f"{card['name']}_knowledge.txt"
            kb_path.write_text(knowledge_base, encoding="utf-8")

        return {
            **card,
            "knowledge_base": knowledge_base,
            "sources_used": list(result["sources"].keys()),
        }
    except Exception as e:
        raise HTTPException(500, f"AI 生成失败，请重试。错误：{e}")


@app.get("/api/character/{name}")
def get_character(name: str):
    """获取单个角色完整信息（含扩展字段）"""
    for path, char in Character.list_available():
        if char.name == name:
            return char.to_dict()
    raise HTTPException(404, f"角色「{name}」不存在")


@app.put("/api/character/update")
def update_character(body: UpdateCharacterBody):
    """更新角色卡（支持改名）"""
    if not body.name.strip():
        raise HTTPException(400, "角色名不能为空")
    safe = re.sub(r'[\\/:*?"<>|]', '', body.name.strip())
    char_file = CHARACTERS_DIR / f"{safe}.json"
    if not char_file.exists():
        raise HTTPException(404, f"角色「{body.name}」不存在")

    final_name = body.new_name.strip() or body.name.strip()
    final_safe = re.sub(r'[\\/:*?"<>|]', '', final_name)
    if not final_safe:
        raise HTTPException(400, "角色名包含非法字符")

    data = {
        "name": final_safe,
        "personality": body.personality,
        "background": body.background,
        "speaking_style": body.speaking_style,
        "relationship_to_user": body.relationship,
        "greeting": body.greeting or f"你好！我是{final_safe}，很高兴认识你～",
        "values": body.values,
        "knowledge_areas": body.knowledge_areas,
        "behavior_rules": body.behavior_rules,
        "emotional_layers": body.emotional_layers,
    }

    # 如果改了名，删旧文件建新文件
    if final_safe != safe:
        char_file.unlink()
        new_file = CHARACTERS_DIR / f"{final_safe}.json"
        if new_file.exists():
            raise HTTPException(400, f"角色「{final_safe}」已存在")
        new_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # 重命名知识库文件
        old_kb = CHARACTERS_DIR / f"{safe}_knowledge.txt"
        if old_kb.exists():
            old_kb.rename(CHARACTERS_DIR / f"{final_safe}_knowledge.txt")
    else:
        char_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"ok": True, "name": final_safe}


@app.delete("/api/character/{name}")
def delete_character(name: str):
    """删除角色卡"""
    safe = re.sub(r'[\\/:*?"<>|]', '', name)
    if not safe:
        raise HTTPException(400, "角色名无效")
    char_file = CHARACTERS_DIR / f"{safe}.json"
    if not char_file.exists():
        raise HTTPException(404, f"角色「{name}」不存在")
    char_file.unlink()
    # 清理知识库文件
    kb_path = CHARACTERS_DIR / f"{safe}_knowledge.txt"
    if kb_path.exists():
        kb_path.unlink()
    return {"ok": True, "message": f"角色「{name}」已删除"}


@app.post("/api/chat")
def chat(req: ChatRequest, background: BackgroundTasks):
    """非流式版（查询重写 + 过滤检索）"""
    if not all([llm, active_char, memory_store, chat_db]):
        raise HTTPException(503, "系统未初始化")
    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 查询重写 — 消除指代
    rewritten = llm.rewrite_query(user_input, chat_db.get_last_n(4))
    memories = memory_store.search(rewritten, n_results=TOP_K_MEMORIES, threshold=SIMILARITY_THRESHOLD)
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_db.get_last_n(MAX_HISTORY_TURNS * 2))
    messages.append({"role": "user", "content": user_input})

    try:
        response = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(500, str(e))

    # 构建上下文给后台任务（当前轮之前的对话）
    ctx = chat_db.get_last_n(4)
    ctx_lines = [f"{'用户' if m['role']=='user' else '角色'}: {m['content']}" for m in ctx]
    context_text = "\n".join(ctx_lines)

    chat_db.add("user", user_input)
    chat_db.add("assistant", response)
    background.add_task(_extract_memory_background, user_input, response, active_char.name, context_text)

    return {
        "reply": response,
        "character_name": active_char.name,
        "memory_count": memory_store.count(),
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, background: BackgroundTasks):
    """流式版（查询重写 + 过滤检索）"""
    if not all([llm, active_char, memory_store, chat_db]):
        raise HTTPException(503, "系统未初始化")
    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 查询重写 — 消除指代
    rewritten = llm.rewrite_query(user_input, chat_db.get_last_n(4))
    memories = memory_store.search(rewritten, n_results=TOP_K_MEMORIES, threshold=SIMILARITY_THRESHOLD)
    system_prompt = active_char.build_system_prompt(memories)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_db.get_last_n(MAX_HISTORY_TURNS * 2))
    messages.append({"role": "user", "content": user_input})

    # 捕获上下文给后台任务（闭包内访问）
    ctx = chat_db.get_last_n(4)
    ctx_lines = [f"{'用户' if m['role']=='user' else '角色'}: {m['content']}" for m in ctx]
    context_text = "\n".join(ctx_lines)

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
        background.add_task(_extract_memory_background, user_input, full_response, active_char.name, context_text)

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


@app.post("/api/memories")
def add_memory(body: AddMemoryBody):
    """手动添加一条记忆"""
    if not memory_store:
        raise HTTPException(503, "记忆系统未初始化")
    if not body.summary.strip():
        raise HTTPException(400, "记忆内容不能为空")
    memory_store.add_memory(
        summary=body.summary,
        facts=body.facts,
        topics=body.topics,
    )
    return {"ok": True, "memory_count": memory_store.count()}


@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: str, body: UpdateMemoryBody):
    """编辑一条记忆"""
    if not memory_store:
        raise HTTPException(503, "记忆系统未初始化")
    memory_store.update_memory(
        memory_id=memory_id,
        summary=body.summary,
        facts=body.facts,
        topics=body.topics,
    )
    return {"ok": True}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    if not memory_store:
        raise HTTPException(503, "记忆系统未初始化")
    memory_store.delete_memory(memory_id)
    return {"ok": True}


@app.delete("/api/history")
def clear_history():
    """清空对话历史"""
    if chat_db:
        chat_db.clear()
    return {"ok": True}


@app.get("/api/export")
def export_history():
    """导出对话记录为 JSON 文件"""
    if not chat_db:
        return []
    from fastapi.responses import JSONResponse
    data = chat_db.get_all()
    return JSONResponse(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=chat_history.json"},
    )


# ============================================================
# 后台任务
# ============================================================
def _extract_memory_background(user_msg: str, assistant_msg: str, character_name: str, context_text: str = ""):
    """后台：提取记忆 → 与旧记忆做冲突检测 → 存入（绑定角色，不依赖全局变量）"""
    # 前一个任务还在跑则跳过本轮，避免重复记忆和资源竞争
    if not _memory_lock.acquire(blocking=False):
        return

    try:
        if context_text:
            history_text = f"{context_text}\n用户: {user_msg}\n角色: {assistant_msg}"
        else:
            history_text = f"用户: {user_msg}\n角色: {assistant_msg}"

        mem_store = MemoryStore(MEMORY_DIR, character_name, api_config=_settings)

        old = mem_store.search_with_ids(assistant_msg, n_results=1, threshold=SIMILARITY_THRESHOLD)
        old_summary = old[0]["summary"] if old else None
        old_id = old[0]["id"] if old else None

        data = llm.extract_memory(history_text, old_memory=old_summary)
        if not data or not data.get("worth") or not data.get("summary"):
            return

        relation = data.get("relation")
        if relation == "duplicate":
            return
        if relation in ("supersedes", "contradicts") and old_id:
            mem_store.add_memory(
                summary=data["summary"],
                facts=data.get("facts", []),
                topics=data.get("topics", []),
                supersedes=old_id,
            )
            return

        mem_store.add_memory(
            summary=data["summary"],
            facts=data.get("facts", []),
            topics=data.get("topics", []),
        )
    finally:
        _memory_lock.release()


# ============================================================
# 静态文件
# ============================================================
app.mount("/", StaticFiles(directory=str(DATA_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
