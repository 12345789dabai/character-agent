# 多用户系统实施计划

## 目标
将单用户系统改造为多用户系统，用户使用自己的 API Key 登录，数据按用户隔离。

## 架构设计

### 认证流程
```
用户输入 API Key + 选择 Provider + Model
    ↓
后端验证 Key 有效性（调用 /v1/models 或发送简单请求）
    ↓
验证通过 → 生成 user_id（API Key 的 SHA256 前16位）
    ↓
返回 auth_token（JWT 或简单 hash）
    ↓
前端存储 token，后续请求带 Authorization header
```

### 数据结构
```
data/
├── users.db                    # 用户数据库（SQLite）
│   ├── users 表：user_id, api_key_encrypted, provider, model, base_url, created_at
├── user_data/
│   ├── {user_id}/
│   │   ├── chat_history.db     # 对话历史
│   │   └── memory_db/          # 记忆文件
├── characters/                  # 公共角色（所有人共享）
│   ├── *.json
│   └── *_knowledge.txt
```

## 实施步骤

### 阶段 1：数据库层（user_db.py）
新建文件，管理用户表：
- `create_user(user_id, api_key, provider, model, base_url)` - 创建/更新用户
- `get_user(user_id)` - 获取用户信息
- `get_user_by_key(api_key)` - 通过 API Key 查找用户
- `list_users()` - 列出所有用户（管理用）

### 阶段 2：认证模块（auth.py）
新建文件，处理认证逻辑：
- `verify_api_key(provider, api_key, model, base_url)` - 验证 API Key 有效性
- `generate_user_id(api_key)` - 生成 user_id
- `generate_token(user_id)` - 生成 auth_token
- `verify_token(token)` - 验证 token

### 阶段 3：改造 web_app.py
- 移除全局状态变量，改为请求级状态
- 新增登录 API：`POST /api/auth/login`
- 新增登出 API：`POST /api/auth/logout`
- 改造中间件：从 cookie/header 读取 token，解析 user_id
- 所有 API 加入 user_id 参数
- 对话历史和记忆按 user_id 隔离

### 阶段 4：改造 memory.py
- MemoryStore 初始化时传入 user_id
- 数据文件路径改为 `user_data/{user_id}/memory_db/{char}_memory.json`

### 阶段 5：改造 chat_db.py
- ChatDB 初始化时传入 user_id
- 数据库路径改为 `user_data/{user_id}/chat_history.db`

### 阶段 6：前端改造（static/index.html）
- 登录页改造：输入 API Key + 选择 Provider + Model
- 移除原来的设置页面（API Key 在登录时配置）
- 保持其他功能不变

### 阶段 7：清理和迁移
- 保留旧数据兼容（可选）
- 更新 README

## 关键文件改动

| 文件 | 改动 |
|------|------|
| `user_db.py` | 新建，用户表管理 |
| `auth.py` | 新建，认证逻辑 |
| `web_app.py` | 大幅改造，多用户支持 |
| `memory.py` | 小改，支持 user_id 参数 |
| `chat_db.py` | 小改，支持 user_id 参数 |
| `config.py` | 小改，新增用户数据目录配置 |
| `static/index.html` | 中等改造，登录页 |
| `llm.py` | 不变 |

## 预计工作量
- 阶段 1-2：1-2 小时
- 阶段 3：2-3 小时
- 阶段 4-5：1 小时
- 阶段 6：2 小时
- 阶段 7：1 小时
- 总计：约 7-9 小时
