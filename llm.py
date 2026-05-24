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
            raise LLMError(
                f"无法连接到 Ollama ({self.base_url})。\n"
                f"请确认 Ollama 已启动：ollama serve"
            )
        except requests.Timeout:
            raise LLMError("LLM 响应超时，请检查模型是否正在运行")

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

    # ──────────────────────────────
    # 流式输出
    # ──────────────────────────────
    def chat_stream(self, messages: list[dict]):
        """流式调用 LLM，逐个 yield 文本块"""
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

    def extract_memory(self, history_text: str) -> dict | None:
        """让 LLM 判断对话是否有价值，并提取记忆"""
        prompt = (
            "你是一个记忆提取助手。根据以下对话，判断是否有值得长期记住的信息。\n\n"
            '"值得记住"指的是：用户的个人信息、偏好、重要事件、正在做的事情、情感状态等。'
            "日常寒暄和无关闲聊不算。\n\n"
            "请严格按 JSON 格式输出：\n"
            '  "worth": true 或 false（是否有值得记住的信息）\n'
            '  "summary": "摘要（一句话，worth 为 false 时留空）"\n'
            '  "facts": ["关键事实1", "关键事实2", ...]\n'
            '  "topics": ["主题1", "主题2", ...]\n\n'
            f"对话内容：\n{history_text}\n\n"
            "只输出 JSON，不要任何其他内容。"
        )
        try:
            resp = self.chat([{"role": "user", "content": prompt}])
            text = resp.strip()

            # 清理可能出现的 markdown 代码块标记
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except Exception:
            return None
