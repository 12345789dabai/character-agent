# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

永久角色对话 Agent — 支持角色扮演的长期记忆对话系统。用户加载角色卡（JSON），与角色聊天，系统自动提取关键信息存入 ChromaDB 向量数据库，下次启动可回忆过往对话。

## 启动命令

```bash
cd character-agent
pip install -r requirements.txt     # 首次安装依赖
python web_app.py                    # 启动 Web 界面（或双击 start.bat）
```

Web 界面访问 http://127.0.0.1:8000，首次打开需在浏览器中配置 API。

## 项目架构

### 入口

- **`web_app.py`** — FastAPI 服务器，提供 REST API + 静态前端。短期记忆由 SQLite 持久化（`chat_db.py`），长期记忆在 ChromaDB（`memory.py`）。后台任务异步提取对话摘要。设置持久化到 `user_settings.json`。

### 核心模块

| 文件 | 职责 |
|------|------|
| `character.py` | 角色卡加载（`Character` 类），从 `characters/*.json` 读取，生成 system prompt |
| `memory.py` | `MemoryStore` 封装 ChromaDB，使用 sentence-transformers 多语言嵌入模型 |
| `llm.py` | `LLM` 类封装 LLM 调用（OpenAI 兼容 / Ollama），支持流式输出 |
| `chat_db.py` | `ChatDB` 封装 SQLite，持久化短期对话历史 |
| `config.py` | 默认配置常量 |

### 关键数据流

```
用户输入 → memory.search() 语义检索 → character.build_system_prompt(记忆)
    → 组装 messages → llm.chat_stream() 逐字返回 → 存入 chat_db
    → 后台: llm.extract_memory() 判断价值 → 去重 → memory.add_memory()
```

### API 路由（web_app.py）

- `GET /api/status` — 服务状态、角色、记忆数量
- `GET/POST /api/settings` — 查看/修改 API 配置
- `GET /api/characters` — 列出所有角色
- `POST /api/character/switch` — 切换角色，重置对话
- `POST /api/character/create` — 创建新角色卡
- `POST /api/chat` — 发送消息（非流式）
- `POST /api/chat/stream` — 发送消息（流式 SSE）
- `GET /api/history` — 获取短期对话历史
- `DELETE /api/history` — 清空对话
- `GET /api/export` — 导出对话 JSON
- `GET /api/memories` — 列出所有长期记忆
- `POST /api/memories` — 手动添加记忆
- `DELETE /api/memories/{id}` — 删除单条记忆

### 角色卡

`characters/*.json` 格式：
```json
{
  "name": "角色名",
  "personality": "性格描述",
  "background": "背景故事",
  "speaking_style": "说话风格",
  "relationship_to_user": "和用户的关系",
  "greeting": "开场白"
}
```

### 注意事项

- ChromaDB 集合名 sanitize：`re.sub(r'[^a-zA-Z0-9_-]', '', name) or 'default'`
- `memory_db/` 和 `chat_history.db` 在 `.gitignore` 中，不会提交到 git
- API Key 明文存储在 `user_settings.json`，同样被 `.gitignore` 过滤
- 首次启动会自动下载 paraphrase-multilingual-MiniLM-L12-v2 嵌入模型（~400MB）
