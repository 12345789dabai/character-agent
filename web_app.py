"""
Web 服务器 — 多用户支持 + 聊天界面 API
"""
import json
import os
import re
import threading
from datetime import datetime
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
from user_db import UserDB
from auth import generate_user_id, generate_token, verify_token, verify_api_key

# ============================================================
# 全局状态
# ============================================================
user_db = UserDB()

# 缓存已创建的用户数据目录
_user_dirs_created: set[str] = set()

SETTINGS_FILE = BASE_DIR / "user_settings.json"

# 后台任务锁（每个用户独立）
_memory_locks: dict[str, threading.Lock] = {}
_memory_lock_lock = threading.Lock()

app = FastAPI(title="永久角色对话 Agent")


def _get_memory_lock(user_id: str) -> threading.Lock:
    """获取用户独立的后台任务锁"""
    with _memory_lock_lock:
        if user_id not in _memory_locks:
            _memory_locks[user_id] = threading.Lock()
        return _memory_locks[user_id]


def _ensure_user_dir(user_id: str):
    """确保用户数据目录存在"""
    if user_id in _user_dirs_created:
        return
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "memory_db").mkdir(exist_ok=True)
    _user_dirs_created.add(user_id)


def _get_user_llm(user_id: str) -> LLM:
    """获取用户的 LLM 实例"""
    user = user_db.get_user(user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    return LLM(
        provider=user["provider"],
        model=user["model"],
        base_url=user["base_url"],
        api_key=user["api_key_encrypted"],  # 已经是明文存储
    )


# ============================================================
# 认证中间件
# ============================================================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 放行公开路由
    public_paths = {"/api/auth/login", "/api/auth/verify"}
    if request.url.path in public_paths:
        return await call_next(request)
    # 放行静态文件
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # 从 cookie 或 header 读取 token
    token = request.cookies.get("auth_token") or ""
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})

    user_id = verify_token(token)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "登录已过期，请重新登录"})

    # 将 user_id 注入到 request.state
    request.state.user_id = user_id
    return await call_next(request)


# ============================================================
# 认证 API
# ============================================================
class LoginBody(BaseModel):
    api_key: str
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = ""


class VerifyBody(BaseModel):
    api_key: str
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = ""


@app.post("/api/auth/verify")
def verify_key(body: VerifyBody):
    """验证 API Key 是否有效"""
    ok, error = verify_api_key(body.provider, body.api_key, body.model, body.base_url)
    if ok:
        return {"ok": True}
    raise HTTPException(400, error)


@app.post("/api/auth/login")
def login(body: LoginBody):
    """登录：验证 API Key → 创建/更新用户 → 返回 token"""
    ok, error = verify_api_key(body.provider, body.api_key, body.model, body.base_url)
    if not ok:
        raise HTTPException(400, f"API Key 验证失败：{error}")

    user_id = generate_user_id(body.api_key)
    _ensure_user_dir(user_id)

    # 创建或更新用户（API Key 明文存储，因为需要用来调用 LLM）
    user_db.create_or_update(
        user_id=user_id,
        api_key_encrypted=body.api_key,  # 存储明文，因为 LLM 调用需要
        provider=body.provider,
        model=body.model,
        base_url=body.base_url.rstrip("/"),
    )

    token = generate_token(user_id)
    resp = JSONResponse({
        "ok": True,
        "user_id": user_id,
        "token": token,
    })
    resp.set_cookie(
        key="auth_token", value=token,
        httponly=True, max_age=30 * 24 * 3600, path="/"
    )
    return resp


@app.get("/api/auth/check")
def check_auth(request: Request):
    """检查登录状态"""
    user_id = request.state.user_id
    user = user_db.get_user(user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    return {
        "ok": True,
        "user_id": user_id,
        "provider": user["provider"],
        "model": user["model"],
    }


@app.post("/api/auth/logout")
def logout():
    """登出"""
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("auth_token", path="/")
    return resp


# ============================================================
# 初始化（获取用户数据）
# ============================================================
def _get_user_components(user_id: str) -> tuple[Character | None, MemoryStore, ChatDB, LLM]:
    """获取用户的组件：角色、记忆、对话历史、LLM"""
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None

    chat_db = ChatDB(str(BASE_DIR), user_id=user_id)
    if active_char:
        chat_db.current_char = active_char.name

    memory_store = MemoryStore(str(BASE_DIR), active_char.name if active_char else "", user_id=user_id)
    llm = _get_user_llm(user_id)

    return active_char, memory_store, chat_db, llm


# ============================================================
# 请求/响应模型
# ============================================================
class ChatRequest(BaseModel):
    message: str


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
def get_status(request: Request):
    user_id = request.state.user_id
    try:
        active_char, memory_store, chat_db, llm = _get_user_components(user_id)
    except Exception:
        return {"configured": False, "character": None, "greeting": "",
                "memory_count": 0, "history_count": 0, "last_message_time": None, "stage": ""}

    last_time = chat_db.last_message_time()
    stage = ""
    try:
        stage = memory_store.get_lifecycle().get_lc().get("阶段名", "")
    except Exception:
        pass

    return {
        "configured": True,
        "character": active_char.name if active_char else None,
        "greeting": active_char.greeting if active_char else "",
        "memory_count": memory_store.count(),
        "history_count": chat_db.count(),
        "last_message_time": last_time,
        "stage": stage,
    }


@app.get("/api/characters")
def list_characters(request: Request):
    return [
        {"name": c.name, "greeting": c.greeting, "relationship": c.relationship}
        for _, c in Character.list_available()
    ]


@app.post("/api/character/switch")
def switch_character(body: CharacterSwitchBody, request: Request):
    """切换角色（保留各自的对话历史）"""
    user_id = request.state.user_id
    for path, char in Character.list_available():
        if char.name == body.name:
            chat_db = ChatDB(str(BASE_DIR), user_id=user_id)
            chat_db.current_char = char.name
            memory_store = MemoryStore(str(BASE_DIR), char.name, user_id=user_id)
            return {
                "ok": True,
                "character": char.name,
                "greeting": char.greeting,
                "memory_count": memory_store.count(),
                "history_count": chat_db.count(),
            }
    raise HTTPException(404, f"角色「{body.name}」不存在")


@app.post("/api/character/create")
def create_character(body: CreateCharacterBody, request: Request):
    """创建新角色卡（公共角色）"""
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
def generate_character(body: GenerateCharacterBody, request: Request):
    """AI 四阶段生成角色卡（搜索 → 分析 → 生成 → 知识库）"""
    user_id = request.state.user_id
    if not body.description.strip():
        raise HTTPException(400, "描述不能为空")

    try:
        llm = _get_user_llm(user_id)
    except Exception:
        raise HTTPException(503, "请先登录")

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
def get_character(name: str, request: Request):
    """获取单个角色完整信息（含扩展字段）"""
    for path, char in Character.list_available():
        if char.name == name:
            return char.to_dict()
    raise HTTPException(404, f"角色「{name}」不存在")


@app.put("/api/character/update")
def update_character(body: UpdateCharacterBody, request: Request):
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
def delete_character(name: str, request: Request):
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
def chat(req: ChatRequest, request: Request, background: BackgroundTasks):
    user_id = request.state.user_id
    active_char, memory_store, chat_db, llm = _get_user_components(user_id)

    if not active_char:
        raise HTTPException(503, "没有可用角色")

    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 时间推进
    lc = memory_store.get_lifecycle()
    last_active = lc.get_lc().get("最后活跃")
    gap = 0
    if last_active:
        try:
            gap = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds()
        except Exception:
            pass
    lc.advance(offline_hours=0, gap_seconds=gap)

    memories = memory_store.format_for_prompt()
    stage_info = memory_store.get_lifecycle().get_stage_prompt(active_char.name)
    system_prompt = active_char.build_system_prompt(memories_text=memories, stage_info=stage_info)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_db.get_last_n(MAX_HISTORY_TURNS * 2))
    messages.append({"role": "user", "content": user_input})

    try:
        response = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(500, str(e))

    chat_db.add("user", user_input)
    chat_db.add("assistant", response)
    background.add_task(_extract_memory_background, user_input, response,
                        active_char.name, user_id)

    return {
        "reply": response,
        "character_name": active_char.name,
        "memory_count": memory_store.count(),
        "stage": lc.get_lc().get("阶段名", ""),
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request, background: BackgroundTasks):
    user_id = request.state.user_id
    active_char, memory_store, chat_db, llm = _get_user_components(user_id)

    if not active_char:
        raise HTTPException(503, "没有可用角色")

    user_input = req.message.strip()
    if not user_input:
        raise HTTPException(400, "消息不能为空")

    # 时间推进
    lc = memory_store.get_lifecycle()
    last_active = lc.get_lc().get("最后活跃")
    gap = 0
    if last_active:
        try:
            gap = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds()
        except Exception:
            pass
    lc.advance(offline_hours=0, gap_seconds=gap)

    memories = memory_store.format_for_prompt()
    stage_info = memory_store.get_lifecycle().get_stage_prompt(active_char.name)
    system_prompt = active_char.build_system_prompt(memories_text=memories, stage_info=stage_info)
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
        background.add_task(_extract_memory_background, user_input, full_response,
                            active_char.name, user_id)

        yield f"data: {json.dumps({'done': True, 'memory_count': memory_store.count(), 'character_name': active_char.name})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
def get_history(request: Request):
    user_id = request.state.user_id
    _, _, chat_db, _ = _get_user_components(user_id)
    return chat_db.get_last_n(MAX_HISTORY_TURNS * 2)


@app.get("/api/memories")
def list_memories(request: Request):
    user_id = request.state.user_id
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None
    if not active_char:
        return {"L0": [], "L1": [], "L2": [], "L3": [], "日志": []}
    ms = MemoryStore(str(BASE_DIR), active_char.name, user_id=user_id)
    return ms.get_all()


@app.post("/api/memories")
def add_memory(body: AddMemoryBody, request: Request):
    user_id = request.state.user_id
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None
    if not active_char:
        raise HTTPException(503, "没有可用角色")
    if not body.summary.strip():
        raise HTTPException(400, "记忆内容不能为空")
    ms = MemoryStore(str(BASE_DIR), active_char.name, user_id=user_id)
    ms.add(content=body.summary, level="L1")
    return {"ok": True, "memory_count": ms.count()}


@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: str, body: UpdateMemoryBody, request: Request):
    user_id = request.state.user_id
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None
    if not active_char:
        raise HTTPException(503, "没有可用角色")
    content = body.summary or ""
    if not content:
        raise HTTPException(400, "内容不能为空")
    ms = MemoryStore(str(BASE_DIR), active_char.name, user_id=user_id)
    ms.update(memory_id=memory_id, content=content)
    return {"ok": True}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str, request: Request):
    user_id = request.state.user_id
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None
    if not active_char:
        raise HTTPException(503, "没有可用角色")
    ms = MemoryStore(str(BASE_DIR), active_char.name, user_id=user_id)
    ms.delete(memory_id)
    return {"ok": True}


@app.delete("/api/history")
def clear_history(request: Request):
    """清空对话历史"""
    user_id = request.state.user_id
    _, _, chat_db, _ = _get_user_components(user_id)
    chat_db.clear()
    return {"ok": True}


@app.get("/api/export")
def export_history(request: Request):
    """导出对话记录为 JSON 文件"""
    user_id = request.state.user_id
    _, _, chat_db, _ = _get_user_components(user_id)
    data = chat_db.get_all()
    return JSONResponse(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=chat_history.json"},
    )


@app.get("/api/ending")
def check_ending(request: Request):
    """检查角色是否到达结局"""
    user_id = request.state.user_id
    chars = Character.list_available()
    active_char = chars[0][1] if chars else None
    if not active_char:
        return {"ending": False}
    try:
        ms = MemoryStore(str(BASE_DIR), active_char.name, user_id=user_id)
        return ms.get_lifecycle().check_ending()
    except Exception:
        return {"ending": False}


# ============================================================
# 后台任务
# ============================================================
def _extract_memory_background(user_msg: str, assistant_msg: str,
                               character_name: str, user_id: str):
    """后台：提取记忆 → 与旧记忆做冲突检测 → 存入"""
    lock = _get_memory_lock(user_id)
    if not lock.acquire(blocking=False):
        return

    try:
        history_text = f"用户: {user_msg}\n角色: {assistant_msg}"

        mem_store = MemoryStore(str(BASE_DIR), character_name, user_id=user_id)
        active = mem_store.get_active()

        # 获取角色信息
        chars = Character.list_available()
        char_traits = ""
        for _, c in chars:
            if c.name == character_name:
                char_traits = c.personality
                break

        # 获取用户的 LLM
        llm = _get_user_llm(user_id)

        data = llm.extract_memory_v2(
            history_text,
            character_name=character_name,
            character_traits=char_traits,
            active_memories=active,
        )
        if not data or not data.get("worth") or not data.get("content"):
            return

        relation = data.get("relation")
        if relation == "duplicate":
            return

        if relation == "supersedes" and data.get("supersedes_id"):
            mem_store.delete(data["supersedes_id"])

        # 根据来源计算最终权重
        source = data.get("source", "chat")
        weight_factor = data.get("weight_factor", 1.0)
        emotion_intensity = data.get("emotion_intensity", 0.5)
        emotion_label = data.get("emotion_label", "")
        WEIGHTS = {"self": 3.0, "user": 1.0, "chat": 0.5}
        final_weight = WEIGHTS.get(source, 1.0) * weight_factor

        # 检查并存储（含重复升级逻辑）
        level = data.get("level", "L3")
        result = mem_store.check_and_upgrade(
            data["content"], level, emotion_intensity=emotion_intensity
        )
        if result["action"] == "add":
            # 新增时更新权重、来源、情绪
            items = mem_store.get_all().get(level, [])
            for m in items:
                if m.get("id") == result["id"]:
                    m["weight"] = final_weight
                    m["source"] = source
                    m["emotion_intensity"] = emotion_intensity
                    break
            mem_store._save()

        # 记录情绪轨道
        if emotion_label:
            mem_store.add_mood(emotion_label, emotion_intensity)

        mem_store.add_log(history_text)
    finally:
        lock.release()


# ============================================================
# 静态文件
# ============================================================
app.mount("/", StaticFiles(directory=str(DATA_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
