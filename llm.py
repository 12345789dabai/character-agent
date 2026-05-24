import json
import requests


class LLMError(Exception):
    pass


class LLM:
    """LLM 调用封装，支持 OpenAI 兼容接口和 Ollama"""

    def __init__(self, provider: str, model: str, base_url: str = "", api_key: str = ""):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def chat(self, messages: list[dict]) -> str:
        if self.provider == "ollama":
            return self._ollama_chat(messages)
        elif self.provider == "openai":
            return self._openai_chat(messages)
        raise LLMError(f"不支持的 LLM 类型: {self.provider}")

    def _ollama_chat(self, messages: list[dict]) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.ConnectionError:
            raise LLMError(f"无法连接到 Ollama ({self.base_url})")
        except requests.Timeout:
            raise LLMError("LLM 响应超时")

    def _openai_chat(self, messages: list[dict]) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key if self.api_key else None, base_url=self.base_url or None)
        try:
            resp = client.chat.completions.create(
                model=self.model, messages=messages, timeout=60
            )
            return resp.choices[0].message.content
        except Exception as e:
            raise LLMError(f"OpenAI 调用失败: {e}")

    def chat_stream(self, messages: list[dict]):
        if self.provider == "ollama":
            yield from self._ollama_stream(messages)
        elif self.provider == "openai":
            yield from self._openai_stream(messages)
        else:
            raise LLMError(f"不支持的 LLM 类型: {self.provider}")

    def _ollama_stream(self, messages: list[dict]):
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
                stream=True, timeout=120,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except requests.ConnectionError:
            raise LLMError(f"无法连接到 Ollama ({self.base_url})")
        except requests.Timeout:
            raise LLMError("LLM 响应超时")

    def _openai_stream(self, messages: list[dict]):
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key if self.api_key else None, base_url=self.base_url or None)
        try:
            stream = client.chat.completions.create(
                model=self.model, messages=messages, stream=True, timeout=120
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            raise LLMError(f"OpenAI 流式调用失败: {e}")

    def rewrite_query(self, user_input: str, history: list[dict]) -> str:
        """结合最近对话改写用户输入，消除指代"""
        turns = history[-4:] if len(history) >= 4 else history
        lines = []
        for msg in turns:
            role = "用户" if msg["role"] == "user" else "你"
            lines.append(f"{role}: {msg['content']}")
        context = "\n".join(lines)

        prompt = (
            "你是一个查询改写助手。根据对话上下文，将用户最新提问改写成独立、完整的搜索查询。\n"
            "改写规则：消除代词（它、这个、那个等），补全省略信息。保持原意。\n"
            "只输出改写后的查询文本，不要任何解释。\n\n"
            f"对话上下文：\n{context}\n\n"
            f"用户最新提问：{user_input}\n"
            "改写结果："
        )
        try:
            return self.chat([{"role": "user", "content": prompt}]).strip()
        except Exception:
            return user_input

    def extract_memory(self, history_text: str, old_memory: str | None = None) -> dict | None:
        """判断对话是否有价值，结合旧记忆做冲突检测和去重"""
        prompt = (
            "你是一个记忆提取助手。根据以下对话，判断是否有值得长期记住的信息。\n\n"
            '"值得记住"指的是：用户的个人信息、偏好、重要事件、正在做的事情、情感状态等。'
            "日常寒暄和无关闲聊不算。\n\n"
            "请严格按 JSON 格式输出：\n"
            '  "worth": true 或 false\n'
            '  "summary": "摘要（一句话）"\n'
            '  "facts": ["关键事实1", ...]\n'
            '  "topics": ["主题1", ...]\n'
            '  "relation": null（无冲突）| "duplicate"（重复）| "supersedes"（覆盖）| "contradicts"（矛盾）\n\n'
        )
        if old_memory:
            prompt += f'已有记忆："{old_memory}"\n判断新信息与此记忆的关系，输出对应的 relation。\n\n'
        prompt += (
            f"对话内容：\n{history_text}\n\n"
            "只输出 JSON，不要任何其他内容。"
        )
        try:
            resp = self.chat([{"role": "user", "content": prompt}])
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception:
            return None
