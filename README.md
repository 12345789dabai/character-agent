# Character Agent

带长期记忆的角色扮演对话系统。加载角色卡，与角色聊天，系统自动提取关键信息存入向量数据库，每次对话都能"记住"你。

## 功能特性

- **角色扮演对话** — 加载角色卡，与不同角色沉浸式聊天
- **长期记忆** — LLM 自动提取对话中的关键信息，存入 ChromaDB 向量数据库，下次对话自动检索
- **查询重写** — 结合对话历史消除指代，提升记忆检索准确率
- **记忆去重与冲突检测** — 新信息与旧记忆重复时自动跳过，矛盾时自动覆盖
- **多角色管理** — 独立对话历史、独立记忆，切换角色不丢失上下文
- **AI 角色生成** — 输入角色描述，AI 联网搜索后自动生成完整角色卡
- **角色编辑与删除** — 随时修改角色信息
- **记忆自动淘汰** — 每个角色记忆超过上限自动淘汰最旧的
- **访问密码保护** — 部署后需密码才能访问
- **移动端适配** — 手机浏览器可正常使用

## 快速开始

```bash
git clone https://github.com/12345789dabai/character-agent.git
cd character-agent
pip install -r requirements.txt
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000`，在设置中配置 API Key 即可开始对话。

## 项目结构

```
character-agent/
├── web_app.py          # FastAPI 服务器 + REST API（含密码中间件）
├── character.py        # 角色卡加载与管理
├── memory.py           # ChromaDB 长期记忆存储（纯 API 嵌入）
├── chat_db.py          # SQLite 短期对话历史
├── llm.py              # LLM 调用封装（OpenAI 兼容）
├── config.py           # 默认配置常量
├── character_generator.py  # AI 角色生成 Pipeline（4 阶段）
├── searcher.py         # 多源搜索引擎（百度百科 + Wikipedia + DuckDuckGo）
├── requirements.txt    # Python 依赖
├── characters/         # 角色卡目录（*.json）和知识库（*_knowledge.txt）
└── static/
    └── index.html      # Web 聊天界面
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python + FastAPI + Uvicorn |
| 向量数据库 | ChromaDB |
| 对话存储 | SQLite |
| 嵌入方式 | OpenAI 兼容 API（text-embedding-3-small / deepseek-embedding） |
| 前端 | 原生 HTML/CSS/JavaScript（响应式布局） |
| 搜索引擎 | DuckDuckGo / 百度百科 / Wikipedia（角色生成时使用） |
| 部署 | 阿里云轻量服务器，systemd 守护进程 |

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/login` | 访问密码验证 |
| GET | `/api/check-auth` | 检查登录状态 |
| GET | `/api/status` | 服务状态 |
| GET | `/api/characters` | 列出角色 |
| POST | `/api/character/switch` | 切换角色 |
| POST | `/api/character/create` | 创建角色 |
| POST | `/api/character/generate` | AI 生成角色 |
| PUT | `/api/character/update` | 更新角色 |
| DELETE | `/api/character/{name}` | 删除角色 |
| POST | `/api/chat/stream` | 流式对话（SSE） |
| GET | `/api/history` | 获取对话历史 |
| GET | `/api/memories` | 查看长期记忆 |
| POST | `/api/memories` | 手动添加记忆 |
| PATCH | `/api/memories/{id}` | 编辑记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |

## 部署

1. 修改 `web_app.py` 中的 `ACCESS_PASSWORD`
2. 创建 `user_settings.json` 配置 API Key
3. 开放服务器 8000 端口
