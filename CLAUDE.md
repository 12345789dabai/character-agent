# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

有记忆和生命感的 AI 角色对话系统。角色有四层记忆（L0-L3）、情绪加权、热度衰减，并随着五阶段生命周期（相遇→告别）自然变化语气。已部署到阿里云，支持密码访问。

## 启动命令

```bash
cd character-agent
pip install -r requirements.txt     # 首次安装依赖
# 创建 .env 文件
echo ACCESS_PASSWORD=your_password > .env
python web_app.py                    # 启动
```

Web 界面访问 http://127.0.0.1:8000

## 项目架构

### 入口

- **`web_app.py`** — FastAPI 服务器，REST API + 静态前端 + 密码鉴权中间件

### 核心模块

| 文件 | 职责 |
|------|------|
| `character.py` | 角色卡加载与管理，生成 system prompt（含阶段信息注入） |
| `memory.py` | 四层记忆存储（L0-L3），情绪加权、热度衰减、写入审查 |
| `lifecycle.py` | 生命周期管理：时间推进、五阶段制、结局检查 |
| `llm.py` | LLM 调用封装（DeepSeek / OpenAI 兼容），记忆提取 |
| `chat_db.py` | SQLite 短期对话历史 |
| `config.py` | 所有配置（记忆层级、权重、生命周期等） |
| `searcher.py` | 多源搜索引擎（角色生成时使用） |
| `character_generator.py` | AI 角色生成四阶段管线 |

### 关键数据流

```
用户消息 → 时间推进 → 记忆检索（按热度排序）
  → 组装 prompt（角色设定 + 阶段信息 + 有效记忆 + 情绪轨道）
  → LLM 回复（流式）→ 存入 chat_db
  → 后台：提取记忆 → 情绪标记 → 去重检查 → 写入 JSON 文件
```

### 记忆系统

四层结构：
- L0 核心信念（永不过期，权重最高）
- L1 重要事实（180天过期）
- L2 一般经历（30天过期）
- L3 日常琐事（3天过期）

叠加机制：
- 自述权重优先：角色自己说的话权重 3.0 vs 用户说的 1.0
- 情绪加权：情绪强度 × 权重
- 热度衰减：0.97 ^ 天数 × (1 + 0.1 × 访问次数)
- 重复升级：同一内容出现 3 次自动升级

### 生命周期

五阶段制（梯度阈值）：
- 相遇（100条） → 相伴（300条） → 成长（300条） → 沉淀（400条） → 告别（500条）

每阶段会向 prompt 注入不同的语气描述，让角色口吻随阶段自然变化。

### 注意事项

- `memory_db/` 为 JSON 文件存储，`.gitignore` 不会提交
- 访问密码通过 `.env` 文件或环境变量 `ACCESS_PASSWORD` 设置
- `user_settings.json`（含 API Key）在 `.gitignore` 中
- 无本地模型依赖，纯 API 方式运行
- 部署服务器使用 venv + nohup 守护进程
