# 🤖 Character Agent

> **有记忆的 AI 角色系统** — 不是聊天机器人，而是有记忆、有生命、有终点的"人"

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌟 项目亮点

- **🧠 分层记忆系统** — 四层记忆（L0核心信念 → L3日常琐事）+ 情绪加权 + 热度衰减
- **🎭 角色扮演对话** — 加载角色卡，与不同角色沉浸式聊天
- **🔄 记忆自动管理** — 去重、冲突检测、自动淘汰，像人一样记忆
- **👥 多用户支持** — 完全隔离的数据，每个用户独立体验
- **🤖 AI 角色生成** — 输入描述，AI联网搜索后自动生成完整角色卡
- **📱 移动端适配** — 手机浏览器可正常使用

## 🚀 线上体验

**体验地址**: http://39.106.182.113:8000

> 输入密码即可体验完整的角色对话功能，包括记忆系统、角色切换、AI角色生成等。

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Web UI    │  │  Mobile UI  │  │   API CLI   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        服务层 (FastAPI)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   认证模块   │  │   对话模块   │  │   记忆模块   │            │
│  │   auth.py   │  │  web_app.py │  │  memory.py  │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        数据层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   SQLite    │  │  JSON 文件   │  │  角色卡目录  │            │
│  │  对话历史   │  │   长期记忆   │  │  角色设定    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

## 🧠 记忆系统详解

### 四层记忆架构

| 层级 | 内容 | 过期时间 | 权重基准 | 例子 |
|------|------|---------|---------|------|
| **L0 核心信念** | 角色的核心价值观、自我认知 | 永不过期 | 3.0 | "我相信善良" |
| **L1 重要事实** | 关键经历、重要关系 | 180天 | 1.5 | "我最好的朋友是小明" |
| **L2 一般经历** | 日常偏好、普通事件 | 30天 | 0.8 | "我吃过一家好吃的火锅" |
| **L3 日常琐事** | 随口一提的小事 | 3天 | 0.3 | "今天好累" |

### 记忆权重计算

```
最终权重 = base_weight × (1 + 0.3 × repeat_count) × (1 + emotion_intensity × 0.8)
```

| 调节因子 | 规则 | 说明 |
|---------|------|------|
| 来源权重 | self=3.0 / user=1.0 / chat=0.5 | 自述优先原则 |
| 重复升级 | 同一内容出现3次自动升级L0 | 反复说的事是真的 |
| 情绪加权 | 强度0.0-1.0，情绪越强记得越牢 | 情绪门控 |
| 热度衰减 | × 0.97^天数，不提慢慢降到底 | 遗忘即泛化 |
| 访问增益 | × (1 + 0.1 × access_count) | 常提的事不会忘 |

### 记忆写入审查

存之前LLM判断三个问题：
1. 这句话符合角色的性格吗？（不符合 → 不存）
2. 重要还是琐碎？（决定L0-L3）
3. 来源是什么？（决定self/user/chat权重）

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/12345789dabai/character-agent.git
cd character-agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置API Key
# 编辑 user_settings.json，填入你的API Key
{
  "api_key": "sk-your-api-key-here",
  "provider": "deepseek",
  "model": "deepseek-chat"
}

# 4. 启动服务
python web_app.py
```

### 访问应用

浏览器打开 `http://127.0.0.1:8000`

## 📁 项目结构

```
character-agent/
├── web_app.py              # FastAPI 服务器 + REST API
├── auth.py                 # 认证模块（API Key + Token）
├── user_db.py              # 用户数据库管理
├── character.py            # 角色卡加载与管理
├── memory.py               # 长期记忆存储（层级记忆 + 热度衰减）
├── chat_db.py              # SQLite 短期对话历史
├── llm.py                  # LLM 调用封装（OpenAI 兼容）
├── config.py               # 默认配置常量
├── lifecycle.py            # 生命周期管理（五阶段制）
├── character_generator.py  # AI 角色生成 Pipeline（4阶段）
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

## 🔧 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端框架 | Python + FastAPI + Uvicorn | 高性能异步框架 |
| 记忆存储 | JSON 文件 | 纯文本，无向量，无embedding |
| 对话存储 | SQLite | 轻量级本地数据库 |
| LLM API | DeepSeek / OpenAI 兼容 | 支持多种模型 |
| 前端 | 原生 HTML/CSS/JavaScript | 响应式布局，移动端适配 |
| 搜索引擎 | DuckDuckGo / 百度百科 / Wikipedia | 角色生成时使用 |
| 部署 | 阿里云轻量服务器 | systemd 守护进程 |

## 📡 API 文档

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

## 🚢 部署指南

### 本地开发

```bash
python web_app.py
```

### 生产部署（阿里云）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
export ACCESS_PASSWORD="your-password"
export API_KEY="sk-your-api-key"

# 3. 后台运行
nohup python web_app.py > server.log 2>&1 &

# 4. 开放端口
# 在阿里云控制台开放 8000 端口
```

### systemd 服务（推荐）

```bash
# 创建服务文件
sudo nano /etc/systemd/system/character-agent.service

# 内容
[Unit]
Description=Character Agent
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/character-agent
ExecStart=/usr/bin/python3 web_app.py
Restart=always

[Install]
WantedBy=multi-user.target

# 启动服务
sudo systemctl enable character-agent
sudo systemctl start character-agent
```

## 🎯 使用示例

### 1. 创建角色

```bash
curl -X POST http://localhost:8000/api/character/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "小智",
    "personality": "善良、好奇、有点自卑",
    "background": "从小在小城市长大，梦想去大城市"
  }'
```

### 2. 开始对话

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，我是陈宇康",
    "character": "小智"
  }'
```

### 3. 查看记忆

```bash
curl http://localhost:8000/api/memories?character=小智
```

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📞 联系方式

- **GitHub**: [@12345789dabai](https://github.com/12345789dabai)
- **项目链接**: https://github.com/12345789dabai/character-agent

---

⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！
