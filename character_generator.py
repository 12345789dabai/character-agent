"""
多阶段角色生成 Pipeline

Stage 1: 深度搜索（多源并行获取角色资料）
Stage 2: 理解分析（LLM 从资料中提取结构化信息）
Stage 3: 生成角色卡（基于分析生成 9 字段增强角色卡）
Stage 4: 生成知识库（角色擅长的领域知识，增强真实感）
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from searcher import search

if TYPE_CHECKING:
    from llm import LLM


# ---------------------------------------------------------------------------
# Stage 1 — 搜索
# ---------------------------------------------------------------------------

def stage_search(name: str) -> tuple[dict, str]:
    """多源搜索，返回 (sources字典, 合并摘要)"""
    sources = search(name)
    merged = _merge_sources(sources)
    return sources, merged


def _merge_sources(sources: dict) -> str:
    """将所有源合并为一段文本"""
    labels = {
        "baidu": "百度百科",
        "wikipedia": "维基百科（中文）",
        "wikipedia_en": "Wikipedia（英文）",
        "web": "网页搜索",
    }
    parts = []
    for key in ["baidu", "wikipedia", "wikipedia_en", "web"]:
        text = sources.get(key)
        if text:
            label = labels.get(key, key)
            parts.append(f"【{label}】\n{text}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Stage 2 — 分析
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """你是一个角色分析专家。根据以下参考资料，分析这个角色的核心特征。

请严格按照以下 JSON 格式输出，不要有任何其他内容：

{{
  "timeline": "关键生平/事迹时间线（100-200字）",
  "personality_traits": ["特质1（如：果敢决断）", "特质2", "特质3", "特质4"],
  "core_values": ["核心价值观1", "核心价值观2", "核心价值观3"],
  "famous_quotes": ["经典语录1", "经典语录2", "经典语录3"],
  "key_relationships": "重要人物关系（50字内）",
  "emotional_complexity": "情感矛盾面描述（如：外表严厉内心柔软），没有则写'无'",
  "knowledge_domains": ["角色擅长的领域1", "领域2", "领域3", "领域4"],
  "behavior_patterns": ["典型行为模式1", "模式2", "模式3"]
}}

参考资料：
{search_text}

用户补充描述：{user_description}

JSON 输出："""


def stage_analyze(search_text: str, user_description: str, llm: "LLM") -> dict:
    """LLM 分析资料，输出结构化分析"""
    prompt = ANALYSIS_PROMPT.format(
        search_text=search_text or "（无搜索结果，根据用户描述和常识分析）",
        user_description=user_description,
    )
    text = llm.chat([{"role": "user", "content": prompt}])
    return _parse_json(text, {
        "timeline": "",
        "personality_traits": [],
        "core_values": [],
        "famous_quotes": [],
        "key_relationships": "",
        "emotional_complexity": "",
        "knowledge_domains": [],
        "behavior_patterns": [],
    })


# ---------------------------------------------------------------------------
# Stage 3 — 生成角色卡
# ---------------------------------------------------------------------------

CARD_PROMPT = """你是一个角色创作专家。基于以下角色分析结果，生成一份立体的角色卡。

要求：
1. 每个字段要具体、有细节，避免空泛描述
2. 性格要有层次：外在表现 / 内在本质 / 矛盾面
3. background 要包含具体经历和时间节点
4. speaking_style 要说明语气、用词习惯、典型句式
5. 必须真实反映角色的价值观和行为模式

请严格按照以下 JSON 格式输出：

{{
  "name": "角色名",
  "personality": "分层次的性格描述（80-120字，包含外在/内在/矛盾面）",
  "background": "有细节的背景故事（150-250字，含关键时间节点）",
  "speaking_style": "说话语气、用词习惯、口头禅、典型句式（40-80字）",
  "relationship_to_user": "和用户的关系定位",
  "greeting": "符合角色身份的开场白",
  "values": "核心价值观和信仰（40-80字）",
  "knowledge_areas": ["领域1", "领域2", "领域3"],
  "behavior_rules": "行为准则：在什么情况下会有什么反应（60-100字）",
  "emotional_layers": "情感层次：表面情绪 / 深层情感 / 矛盾心理（40-80字）"
}}

分析结果：
{analysis_json}

用户原始描述：{user_description}

JSON 输出："""


def stage_generate_card(analysis: dict, user_description: str, llm: "LLM") -> dict:
    """基于分析结果生成 9 字段角色卡"""
    prompt = CARD_PROMPT.format(
        analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2),
        user_description=user_description,
    )
    text = llm.chat([{"role": "user", "content": prompt}])

    default_card = {
        "name": "",
        "personality": "",
        "background": "",
        "speaking_style": "",
        "relationship_to_user": "",
        "greeting": "",
        "values": "",
        "knowledge_areas": [],
        "behavior_rules": "",
        "emotional_layers": "",
    }
    return _parse_json(text, default_card)


# ---------------------------------------------------------------------------
# Stage 4 — 生成知识库
# ---------------------------------------------------------------------------

KNOWLEDGE_PROMPT = """你是角色知识库生成专家。基于以下角色分析，生成该角色"应该知道的知识"。

这份知识库将注入到角色的 system prompt 中，让角色在对话时能展现出真实的专业素养和知识储备。

要求：
1. 只包含角色确实应该知道的知识（基于其身份、时代、专业领域）
2. 用第一人称（"我..."）书写，符合角色身份
3. 分领域组织，每个领域 3-5 个关键知识点
4. 用简洁的一句话描述每个知识点
5. 总字数 300-500 字

角色分析：
{analysis_json}

角色卡：
{card_json}

知识库内容："""


def stage_generate_knowledge(analysis: dict, card: dict, llm: "LLM") -> str:
    """生成角色知识库文本"""
    prompt = KNOWLEDGE_PROMPT.format(
        analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2),
        card_json=json.dumps(card, ensure_ascii=False, indent=2),
    )
    text = llm.chat([{"role": "user", "content": prompt}])
    return text.strip()


# ---------------------------------------------------------------------------
# Pipeline 入口
# ---------------------------------------------------------------------------

def generate_character(description: str, llm: "LLM", char_name: str | None = None) -> dict:
    """四阶段 Pipeline：搜索 → 分析 → 生成 → 知识库

    Returns:
        {
            "card": {...},           # 角色卡 dict
            "knowledge_base": "...",  # 知识库文本
            "sources": {...},         # 搜索来源
            "search_used": bool,
        }
    """
    # Stage 1 — 搜索
    if char_name:
        query = char_name
    else:
        # 从描述中提取可能的角色名（取第一段最前面的名词）
        query = description.strip().split()[0] if description.strip() else ""

    sources, merged_text = stage_search(query)
    search_used = bool(merged_text)

    # Stage 2 — 分析
    analysis = stage_analyze(merged_text, description, llm)

    # Stage 3 — 生成角色卡
    card = stage_generate_card(analysis, description, llm)
    # 修复名字：拒绝占位符，优先从描述提取
    raw_name = card.get("name", "")
    if not raw_name or raw_name in ("角色名", "角色", "姓名", "name", "未命名"):
        card["name"] = _extract_name(description, char_name)

    # Stage 4 — 生成知识库
    knowledge = stage_generate_knowledge(analysis, card, llm)

    return {
        "card": card,
        "knowledge_base": knowledge,
        "sources": sources,
        "search_used": search_used,
    }


# ---------------------------------------------------------------------------
# JSON 解析工具
# ---------------------------------------------------------------------------

def _extract_name(description: str, fallback: str | None = None) -> str:
    """从描述中提取最可能的角色名"""
    # 尝试匹配中文人名模式（2-4个中文字符，常见姓氏开头）
    import re as _re
    # 常见姓氏列表
    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅"  # noqa: E501
    m = _re.search(rf'[{surnames}]([一-鿿]{{1,3}})', description)
    if m:
        return m.group(0)

    # 尝试匹配2-4个中文字符的连续名字
    m = _re.search(r'[一-鿿]{2,4}', description)
    if m:
        return m.group(0)

    # 取第一个非空词汇
    for sep in "，,、 ；;:：":
        description = description.replace(sep, " ")
    parts = [p for p in description.strip().split() if p and len(p) < 20]
    for p in parts:
        if not p.startswith("一个") and len(p) >= 2:
            return p

    return fallback or "助手"


def _parse_json(text: str, default: dict) -> dict:
    """宽容 JSON 解析，三级兜底"""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fixed = re.sub(r',\s*}', '}', text)
        fixed = re.sub(r',\s*]', ']', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # 正则兜底：提取 "key": "value" 对
            data = dict(default)
            pairs = re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', text)
            for key, value in pairs:
                data[key] = value
            # 尝试提取数组
            for key in data:
                arr = re.findall(rf'"{key}"\s*:\s*\[(.*?)\]', text, re.DOTALL)
                if arr:
                    items = re.findall(r'"([^"]*)"', arr[0])
                    if items:
                        data[key] = items
            return data
