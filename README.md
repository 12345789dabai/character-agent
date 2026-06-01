# Character Agent

带长期记忆的角色扮演对话系统。加载角色卡，与角色聊天，系统自动提取关键信息存入数据库，每次对话都能"记住"你。

## 功能特性

- **多用户支持** — 每个用户使用自己的 API Key 登录，数据完全隔离
- **角色扮演对话** — 加载角色卡，与不同角色沉浸式聊天
- **长期记忆** — LLM 自动提取对话中的关键信息，存入本地数据库，下次对话自动检索
- **查询重写** — 结合对话历史消除指代，提升记忆检索准确率
- **记忆去重与冲突检测** — 新信息与旧记忆重复时自动跳过，矛盾时自动覆盖
- **多角色管理** — 独立对话历史、独立记忆，切换角色不丢失上下文
- **AI 角色生成** — 输入角色描述，AI 联网搜索后自动生成完整角色卡
- **角色编辑与删除** — 随时修改角色信息
- **记忆自动淘汰** — 每个角色记忆超过上限自动淘汰最旧的
- **移动端适配** — 手机浏览器可正常使用

## 快速开始

```bash
git clone https://github.com/12345789dabai/character-agent.git
cd character-agent
pip install -r requirements.txt
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000`，输入你的 API Key 即可开始对话。

## 项目结构

```
character-agent/
├── web_app.py              # FastAPI 服务器 + REST API（多用户支持）
├── auth.py                 # 认证模块（API Key 验证 + Token 管理）
├── user_db.py              # 用户数据库管理
├── character.py            # 角色卡加载与管理
├── memory.py               # 长期记忆存储（层级记忆 + 热度衰减）
├── chat_db.py              # SQLite 短期对话历史
├── llm.py                  # LLM 调用封装（OpenAI 兼容）
├── config.py               # 默认配置常量
├── lifecycle.py            # 生命周期管理（五阶段制）
├── character_generator.py  # AI 角色生成 Pipeline（4 阶段）
├── searcher.py             # 多源搜索引擎（百度百科 + Wikipedia + DuckDuckGo）
├── requirements.txt        # Python 依赖
├── characters/             # 角色卡目录（*.json）和知识库（*_knowledge.txt）
├── user_data/              # 用户数据目录（按 user_id 隔离）
│   └── {user_id}/
│       ├── chat_history.db # 对话历史
│       └── memory_db/      # 记忆文件
└── static/
    └── index.html          # Web 聊天界面
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python + FastAPI + Uvicorn |
| 数据库 | SQLite（用户表 + 对话历史） |
| 记忆存储 | JSON 文件（层级记忆 + 热度衰减） |
| 前端 | 原生 HTML/CSS/JavaScript（响应式布局） |
| 搜索引擎 | DuckDuckGo / 百度百科 / Wikipedia（角色生成时使用） |
| 部署 | 阿里云轻量服务器，nohup 守护进程 |

## 多用户架构

### 认证流程

```
用户输入 API Key → 验证 Key 有效性 → 生成 user_id（SHA256 前16位）
    → 返回 auth_token（HMAC-SHA256）→ Cookie 存储
    → 后续请求自动携带 token
```

### 数据隔离

- 每个用户的数据完全隔离
- 对话历史：`user_data/{user_id}/chat_history.db`
- 记忆文件：`user_data/{user_id}/memory_db/`
- 角色卡：公共目录 `characters/`（所有用户共享）

## API 概览

### 认证相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录（验证 API Key） |
| POST | `/api/auth/verify` | 验证 API Key 是否有效 |
| GET | `/api/auth/check` | 检查登录状态 |
| POST | `/api/auth/logout` | 登出 |

### 对话相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 服务状态 |
| POST | `/api/chat/stream` | 流式对话（SSE） |
| GET | `/api/history` | 获取对话历史 |
| DELETE | `/api/history` | 清空对话历史 |
| GET | `/api/export` | 导出对话记录 |

### 角色相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/characters` | 列出角色 |
| POST | `/api/character/switch` | 切换角色 |
| POST | `/api/character/create` | 创建角色 |
| POST | `/api/character/generate` | AI 生成角色 |
| GET | `/api/character/{name}` | 获取角色信息 |
| PUT | `/api/character/update` | 更新角色 |
| DELETE | `/api/character/{name}` | 删除角色 |

### 记忆相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memories` | 查看长期记忆 |
| POST | `/api/memories` | 手动添加记忆 |
| PATCH | `/api/memories/{id}` | 编辑记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |

## 部署

1. 安装依赖：`pip install -r requirements.txt`
2. 启动服务：`python web_app.py`
3. 开放服务器 8000 端口
4. 用户访问后输入自己的 API Key 即可使用

## 开发

```bash
# 本地开发
python web_app.py

# 测试 API
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-xxx", "provider": "openai", "model": "gpt-4o-mini"}'
```

## 许可证

MIT License
