# Character Agent

永久角色对话 Agent — 一个带长期记忆的角色扮演对话系统。

用户加载角色卡，与角色聊天，系统自动提取关键信息存入向量数据库，下次启动可回忆过往对话。

## 功能特性

- **角色扮演对话** — 加载角色卡（JSON），与不同角色沉浸式聊天
- **长期记忆** — 自动提取对话中的关键信息，存入 ChromaDB 向量数据库，下次启动仍可回忆
- **多角色管理** — 独立对话历史、独立记忆系统，切换角色不丢失上下文
- **AI 角色生成** — 输入角色描述，AI 自动生成完整角色卡（支持联网搜索丰富信息）
- **角色编辑与删除** — 随时修改角色信息或删除角色
- **多后端支持** — 兼容 OpenAI 兼容接口和 Ollama 本地模型
- **记忆淘汰** — 每个角色的记忆超过上限自动淘汰最旧的
- **Web 界面** — 简洁的浏览器聊天界面，无需安装额外客户端

## 快速开始

### 方式一：源码运行

```bash
# 1. 克隆项目
git clone https://github.com/12345789dabai/character-agent.git
cd character-agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000`，首次使用需在设置中配置 API。

### 方式二：Windows 一键启动

双击 `start.bat`，自动启动服务并打开浏览器。

## API 配置

支持以下模式：

| 模式 | 说明 |
|------|------|
| **OpenAI** | 使用 OpenAI 兼容 API（需 API Key） |
| **Ollama** | 连接本地 Ollama 服务（无需 API Key） |

在 Web 界面右上角打开「设置」进行配置。

## 角色卡

角色卡为 `characters/*.json` 格式的 JSON 文件：

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

可在 Web 界面中直接创建、编辑和删除角色。

## 项目结构

```
character-agent/
├── web_app.py          # FastAPI 服务器 + REST API
├── character.py        # 角色卡加载与管理
├── memory.py           # ChromaDB 长期记忆存储
├── chat_db.py          # SQLite 短期对话历史
├── llm.py              # LLM 调用封装（OpenAI / Ollama）
├── config.py           # 默认配置常量
├── launcher.py         # 打包入口
├── start.bat           # Windows 一键启动脚本
├── build.bat           # 打包 exe 脚本
├── requirements.txt    # Python 依赖
├── characters/         # 角色卡目录（*.json）
├── static/             # 前端静态文件
│   └── index.html      # Web 聊天界面
├── memory_db/          # ChromaDB 数据目录（gitignore）
└── chat_history.db     # SQLite 数据库文件（gitignore）
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 服务状态 |
| GET/POST | `/api/settings` | 查看/修改配置 |
| GET | `/api/characters` | 列出角色 |
| POST | `/api/character/switch` | 切换角色 |
| POST | `/api/character/create` | 创建角色 |
| POST | `/api/character/generate` | AI 生成角色 |
| GET | `/api/character/{name}` | 获取角色详情 |
| PUT | `/api/character/update` | 更新角色 |
| DELETE | `/api/character/{name}` | 删除角色 |
| POST | `/api/chat` | 发送消息 |
| POST | `/api/chat/stream` | 流式对话 SSE |
| GET | `/api/history` | 获取对话历史 |
| DELETE | `/api/history` | 清空对话 |
| GET | `/api/memories` | 查看长期记忆 |
| POST | `/api/memories` | 手动添加记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |

## 技术栈

- **后端**：Python + FastAPI + Uvicorn
- **向量数据库**：ChromaDB + sentence-transformers（多语言嵌入模型）
- **前端**：原生 HTML/CSS/JavaScript
- **LLM**：兼容 OpenAI API / Ollama
- **搜索引擎**：DuckDuckGo（AI 生成角色时辅助获取信息）

## 依赖

- Python 3.9+
- 首次启动自动下载嵌入模型（~400MB）
