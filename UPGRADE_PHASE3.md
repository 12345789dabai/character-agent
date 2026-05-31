# Phase 3 升级方案：生命周期 + 双向对等记忆

## 总体工作量

| 模块 | 改动的文件 | 代码量 | 难度 |
|------|-----------|--------|------|
| ① 时间推进 | `memory.py`, `web_app.py`, `config.py` | ~40行 | 低 |
| ② 年龄状态 | `character.py`, `web_app.py` | ~15行 | 低 |
| ③ 前端年龄显示 | `index.html` | ~10行 | 低 |
| ④ 角色四象限 | `character.py`, `memory.py` | ~20行 | 低 |
| ⑤ 离线经历生成 | `llm.py`, `web_app.py` | ~30行 | 中 |
| ⑥ 结局触发 | `web_app.py`, `index.html` | ~40行 | 低 |
| ⑦ 告别报告 | `llm.py`, `web_app.py`, `index.html` | ~50行 | 中 |
| ⑧ 角色卡模板 | `characters/` | 按角色而定 | 低 |

**总计：约 200 行核心改动，分 3-4 周实现。**

---

## 第一步：时间推进（3 天）

### 1.1 config.py 新增

```python
# ---------- 生命周期配置 ----------
TIME_PER_MESSAGE = 10        # 每条消息推进（分钟）
TIME_ONLINE_GAP_MULTIPLIER = 2   # 在线间隔倍率
TIME_OFFLINE_HOUR_TO_DAY = 1     # 离线每1小时=角色1天
```

### 1.2 memory.py 新增字段

在 `_data` 中增加：

```python
{
    "生命周期配置": {
        "初始年龄": 18,
        "当前年龄": 18,
        "年龄_minutes": 0,          # 以分钟计的累计年龄
        "固定结局": false,
        "已知结局年龄": null,
        "已知结局描述": "",
        "最后活跃": null,
        "最后离线生成": null,
        "阶段状态": ""
    }
}
```

### 1.3 memory.py 新增方法

```python
def advance_time(self, offline_hours: float = 0, is_active_chat: bool = True):
    """
    推进角色时间
    - 在线聊天: TIME_PER_MESSAGE 分钟
    - 在线但间隔: 间隔时间 × TIME_ONLINE_GAP_MULTIPLIER
    - 离线: offline_hours × TIME_OFFLINE_HOUR_TO_DAY
    """
    cfg = self._data.setdefault("生命周期配置", {})
    cfg.setdefault("年龄_minutes", 0)
    cfg.setdefault("初始年龄", 18)

    if is_active_chat and offline_hours < 0.1:
        advance = TIME_PER_MESSAGE
    elif is_active_chat:
        advance = offline_hours * 60 * TIME_ONLINE_GAP_MULTIPLIER
    else:
        advance = offline_hours * 60 * TIME_OFFLINE_HOUR_TO_DAY

    cfg["年龄_minutes"] += advance
    cfg["当前年龄"] = cfg["初始年龄"] + cfg["年龄_minutes"] / (365 * 24 * 60)
    cfg["最后活跃"] = datetime.now().isoformat()
    self._save()
    return cfg["当前年龄"]

def get_age_stage(self) -> str:
    """获取年龄段标签"""
    age = self._data.get("生命周期配置", {}).get("当前年龄", 18)
    stages = self._data.get("生命周期配置", {}).get("阶段状态", "")
    for range_str, label in stages.items():
        parts = range_str.split("-")
        if len(parts) == 2:
            low, high = int(parts[0]), int(parts[1])
            if low <= age <= high:
                return label
    return ""
```

### 1.4 web_app.py 修改

在每次用户发消息前调用：

```python
# 在 chat() 和 chat_stream() 的入口处
last_active = memory_store._data.get("生命周期配置", {}).get("最后活跃")
offline = 0
if last_active:
    offline = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds() / 3600
current_age = memory_store.advance_time(offline_hours=offline, is_active_chat=True)
```

---

## 第二步：年龄显示（1 天）

### 2.1 web_app.py

在 `/api/status` 返回中增加：

```python
{
    "current_age": round(memory_store.get_age(), 1),
    "age_stage": memory_store.get_age_stage()
}
```

### 2.2 index.html

在角色名旁边显示年龄：

```html
<select id="char-select" ...></select>
<span id="char-age" style="font-size:13px;color:#999;margin-left:6px;"></span>
```

```javascript
// 收到 status 后
if (data.current_age) {
    document.getElementById('char-age').textContent =
        `(${Math.floor(data.current_age)}岁)`;
}
```

---

## 第三步：角色四象限（2 天）

### 3.1 角色卡扩展

```json
{
    "生命周期": {
        "时间推进": true,
        "固定结局": false,
        "已知结局": null,
        "已知结局年龄": null,
        "意外允许": true
    },
    "年龄段状态": {
        "18-22": "青涩、不安、对未来既期待又害怕",
        "23-30": "职场打拼、开始成熟、有点疲惫",
        "31-45": "稳重、事业上升、开始思考人生得失",
        "46-60": "平和、怀旧、珍惜老朋友的陪伴"
    }
}
```

### 3.2 memory.py 迁移

在 `_migrate()` 中从角色卡读取生命周期配置：

```python
def load_lifecycle_from_char(self, char: "Character"):
    lc = getattr(char, 'lifecycle', {})
    self._data.setdefault("生命周期配置", {})
    self._data["生命周期配置"]["固定结局"] = lc.get("固定结局", False)
    self._data["生命周期配置"]["已知结局年龄"] = lc.get("已知结局年龄")
    self._data["生命周期配置"]["已知结局描述"] = lc.get("已知结局", "")
    self._data["生命周期配置"]["当前年龄"] = lc.get("初始年龄", 18)
```

---

## 第四步：离线经历生成（3 天）

### 4.1 llm.py 新增方法

```python
def generate_offline_life(self, character_name: str, age: float,
                          age_stage: str, offline_days: float,
                          recent_memories: list[dict]) -> str:
    mem_text = "\n".join([
        f"- {m.get('content', '')}" for m in recent_memories[:5]
    ]) if recent_memories else "无特别记录"

    prompt = (
        f"你扮演{character_name}，现在你{age:.0f}岁了。\n"
        f"你目前的人生阶段：{age_stage}\n"
        f"现实时间过了{offline_days:.0f}天。\n"
        f"这段时间你经历了什么？请用第一人称写1-2句话。\n"
        f"要求：自然、日常、符合你的年龄和性格。\n"
        f"参考你的记忆：{mem_text}\n"
        "只输出你说的那句话，不要解释。"
    )
    try:
        return self.chat([{"role": "user", "content": prompt}])
    except Exception:
        return ""
```

### 4.2 web_app.py

用户上线时检测离线时长，如果超过阈值则生成离线经历：

```python
# 在时间推进之后
offline_days = offline / 24
if offline_days > 1 and memory_store._data.get("最后离线生成") != today:
    # 需要生成离线经历
    age_stage = memory_store.get_age_stage()
    life_text = llm.generate_offline_life(
        active_char.name, current_age, age_stage, offline_days, memories
    )
    if life_text:
        # 作为开场白注入
        offline_greeting = life_text
    memory_store._data["最后离线生成"] = today
```

---

## 第五步：结局触发（3 天）

### 5.1 web_app.py

```python
@app.get("/api/ending")
def check_ending():
    """检查是否到达结局"""
    if not memory_store:
        return {"ending": False}
    lc = memory_store._data.get("生命周期配置", {})
    if lc.get("固定结局") and lc.get("已知结局年龄"):
        if lc.get("当前年龄", 18) >= lc.get("已知结局年龄"):
            return {
                "ending": True,
                "type": "historical",
                "description": lc.get("已知结局描述", ""),
                "age": round(lc.get("当前年龄", 0), 1)
            }
    return {"ending": False}
```

### 5.2 index.html

在收到 ending=true 时切换界面：

```javascript
async function checkEnding() {
    const res = await fetch('/api/ending');
    const data = await res.json();
    if (data.ending) {
        // 隐藏聊天界面
        document.getElementById('main').style.display = 'none';
        // 显示结局页面
        showEndingPage(data);
    }
}

// 每次 chat 完成时调用
```

结局页面 HTML：

```html
<div id="ending-page" class="hidden">
  <div class="ending-content">
    <h2>尾声</h2>
    <p class="ending-text">{告别报告}</p>
    <div class="ending-stats">
      <div>相伴 {{total_days}} 天</div>
      <div>对话 {{total_messages}} 轮</div>
      <div>共同记忆 {{memory_count}} 条</div>
    </div>
    <button onclick="newGamePlus()">开启新的故事</button>
  </div>
</div>
```

---

## 第六步：告别报告（3 天）

### 6.1 llm.py

```python
def generate_farewell(self, character_name: str, memories: list[dict],
                      mood_track: list[dict], message_count: int) -> str:
    """生成角色的告别报告"""
    top_memories = sorted(memories, key=lambda m: -m.get("weight", 0))[:5]
    mem_lines = "\n".join([
        f"- {m.get('content', '')}（重要度：{m.get('weight', 0):.1f}）"
        for m in top_memories
    ])
    mood_summary = ""
    if mood_track:
        avg = sum(e.get("intensity", 0.5) for e in mood_track) / len(mood_track)
        if avg > 0.6: mood_summary = "大部分时光是快乐的"
        else: mood_summary = "有过欢笑也有过眼泪"

    prompt = (
        f"你是{character_name}，即将走到生命的终点。\n"
        f"这是你一生中最重要的回忆：\n{mem_lines}\n\n"
        f"整体来说，{mood_summary}。共陪伴了{message_count}轮对话。\n\n"
        "请以你的视角，写一段告别的话。要求：\n"
        "- 用第一人称\n"
        "- 真诚、自然，不煽情\n"
        "- 回忆一个具体的细节（选最重要的一条记忆）\n"
        "- 最后给对方一句祝福\n"
        "100-200字。"
    )
    try:
        return self.chat([{"role": "user", "content": prompt}])
    except Exception:
        return ""
```

---

## 实施顺序

| 周次 | 内容 | 前提 |
|------|------|------|
| 第 1 周 | 时间推进 + 年龄显示 | 无 |
| 第 2 周 | 角色四象限 + 角色卡改造 | 第 1 周完成 |
| 第 3 周 | 离线经历生成 + 双向对等 | 第 2 周完成 |
| 第 4 周 | 结局触发 + 告别报告 | 第 3 周完成 |

---

## 测试清单

- [ ] 时间推进：聊 50 条消息，检查年龄是否增长约 8 小时
- [ ] 离线推进：一天不上线，回到来年龄推进约 1 个月
- [ ] 年龄显示：前端正确显示角色年龄和阶段标签
- [ ] 历史人物：诸葛亮在 54 岁正确触发结局
- [ ] 原创角色：不在 54 岁错误触发（没有固定结局）
- [ ] 离线经历：离线超过 1 天后上线，角色有合理的"这段时间做了什么"
- [ ] 结局页面：正确展示告别报告和统计
- [ ] New Game+：结局后能重新开始新角色
- [ ] 防滥用：用户说不合理的内容不会破坏记忆
