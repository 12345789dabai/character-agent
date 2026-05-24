# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

永久角色对话 Agent — 支持角色扮演的长期记忆对话系统。用户加载角色卡（JSON），与角色聊天，系统自动提取关键信息存入 ChromaDB 向量数据库，下次启动可回忆过往对话。

## 启动命令

```bash
cd character-agent
pip install -r requirements.txt     # 首次安装依赖
python web_app.py                    # Web 界面（推荐）
python main.py                       # CLI 模式
```

Web 界面访问 http://127.0.0.1:8000，首次打开需在浏览器中配置 API。

## 项目架构

### 入口

- **`web_app.py`** — FastAPI 服务器，提供 REST API + 静态前端。全局状态（短期记忆）在内存中，长期记忆在 ChromaDB。后台任务 `_extract_memory_background` 异步提取对话摘要。设置持久化到 `user_settings.json`。
- **`main.py`** — CLI 版本，逻辑与 web_app 相同但无后台任务支持。

### 核心模块

| 文件 | 职责 |
|------|------|
| `character.py` | 角色卡加载（`Character` 类），从 `characters/*.json` 读取，生成 system prompt |
| `memory.py` | `MemoryStore` 封装 ChromaDB，使用 sentence-transformers 多语言嵌入模型。集合名只允许 ASCII，中文角色名会被自动 sanitize |
| `llm.py` | `LLM` 类封装 LLM 调用（OpenAI 兼容 / Ollama）。`extract_memory()` 通过 LLM 自己提炼对话摘要为 JSON |

### 关键数据流

```
用户输入 → memory.search() 语义检索 → character.build_system_prompt(记忆)
    → 组装 messages → llm.chat() → 返回回复
    → 每 3 轮: llm.extract_memory() → memory.add_memory() (后台)
```

### API 路由（web_app.py）

- `GET /api/status` — 服务状态、角色、记忆数量
- `GET/POST /api/settings` — 查看/修改 API 配置（provider, api_key, model, base_url）
- `POST /api/chat` — 发送消息，返回回复
- `GET /api/memories` — 列出所有长期记忆
- `DELETE /api/memories/{id}` — 删除单条记忆
- `GET /api/history` — 获取短期对话历史

### 前端

- `static/index.html` — 单页应用，纯 Vanilla JS + CSS。状态：启动时检查 `/api/status` → 未配置弹出设置弹窗 → 已配置进入聊天。侧边栏展示记忆列表，支持删除。

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

### 配置

- `config.py` — 默认值（路径、间隔、模型名），实际运行时可被 `user_settings.json` 覆盖
- `user_settings.json` — 自动生成，存 API Key、模型、地址（API Key 明文存储）

### ChromaDB 注意事项

- 集合名 sanitize 规则：`re.sub(r'[^a-zA-Z0-9_-]', '', name) or 'default'`
- `memory_db/` 目录可删除重建（丢失长期记忆），不影响代码
- 首次启动会自动下载 paraphrase-multilingual-MiniLM-L12-v2 嵌入模型（~400MB）
