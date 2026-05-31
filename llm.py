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

    def _api_base(self) -> str:
        url = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        return url

    @staticmethod
    def _content_to_str(content) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text") or block.get("content") or "")
                else:
                    parts.append(str(block))
            return "\n".join(p for p in parts if p)
        return str(content)

    @staticmethod
    def _prepare_messages(messages: list[dict]) -> list[dict]:
        """仅保留 user/assistant，system/developer 合并进首条 user"""
        system_parts = []
        chat = []
        for m in messages:
            role = m.get("role")
            content = LLM._content_to_str(m.get("content"))
            if role in ("system", "developer"):
                system_parts.append(content)
            elif role == "user":
                chat.append({"role": "user", "content": content})
            elif role == "assistant":
                chat.append({"role": "assistant", "content": content})

        if system_parts:
            system_text = "\n\n".join(system_parts)
            for i, m in enumerate(chat):
                if m["role"] == "user":
                    chat[i] = {"role": "user", "content": f"{system_text}\n\n{m['content']}"}
                    break
            else:
                chat.insert(0, {"role": "user", "content": system_text})

        merged = []
        for m in chat:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n\n" + m["content"]
            else:
                merged.append({"role": m["role"], "content": m["content"]})

        if merged and merged[0]["role"] == "assistant":
            merged.insert(0, {"role": "user", "content": "请继续我们的对话。"})

        for i, m in enumerate(merged):
            if m["role"] not in ("user", "assistant"):
                raise LLMError(f"消息格式错误: messages[{i}].role={m['role']!r}")

        return merged

    def chat(self, messages: list[dict]) -> str:
        messages = self._prepare_messages(messages)
        if self.provider == "ollama":
            return self._ollama_chat(messages)
        elif self.provider == "openai":
            return self._openai_chat(messages)
        raise LLMError(f"不支持的 LLM 类型: {self.provider}")

    def _ollama_chat(self, messages: list[dict]) -> str:
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.ConnectionError:
            raise LLMError(f"无法连接到 Ollama ({self.base_url})")
        except requests.Timeout:
            raise LLMError("LLM 响应超时")
        except requests.HTTPError as e:
            raise LLMError(self._http_error(e.response))

    def _openai_chat(self, messages: list[dict]) -> str:
        url = f"{self._api_base()}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"model": self.model, "messages": messages},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.ConnectionError:
            raise LLMError(f"无法连接到 API ({self.base_url})")
        except requests.Timeout:
            raise LLMError("LLM 响应超时")
        except requests.HTTPError as e:
            raise LLMError(self._http_error(e.response))
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"API 返回格式异常: {e}")

    def chat_stream(self, messages: list[dict]):
        messages = self._prepare_messages(messages)
        if self.provider == "ollama":
            yield from self._ollama_stream(messages)
        elif self.provider == "openai":
            yield from self._openai_stream(messages)
        else:
            raise LLMError(f"不支持的 LLM 类型: {self.provider}")

    def _ollama_stream(self, messages: list[dict]):
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/api/chat",
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
        except requests.HTTPError as e:
            raise LLMError(self._http_error(e.response))

    def _openai_stream(self, messages: list[dict]):
        url = f"{self._api_base()}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": True},
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta
        except requests.ConnectionError:
            raise LLMError(f"无法连接到 API ({self.base_url})")
        except requests.Timeout:
            raise LLMError("LLM 响应超时")
        except requests.HTTPError as e:
            raise LLMError(self._http_error(e.response))

    @staticmethod
    def _http_error(response: requests.Response | None) -> str:
        if response is None:
            return "HTTP 请求失败"
        try:
            body = response.json()
            err = body.get("error")
            if isinstance(err, dict):
                return err.get("message") or str(err)
            if isinstance(err, str):
                return err
            return response.text[:500] or f"HTTP {response.status_code}"
        except Exception:
            return response.text[:500] or f"HTTP {response.status_code}"

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

    def extract_memory_v2(self, conversation: str, character_name: str = "",
                          character_traits: str = "", active_memories: list[dict] | None = None) -> dict | None:
        """记忆提取：自述权重 → 记忆分级 → 性格符合度检查"""
        existing = ""
        if active_memories:
            lines = []
            for m in active_memories[:20]:
                lvl = m.get("level", "L3")
                w = m.get("weight", 1.0)
                s = m.get("source", "")
                tag = "(自己说的)" if s == "self" else ""
                lines.append(f"- [{lvl}] w={w} {m.get('content', '')} {tag}".strip())
            existing = "\n".join(lines)

        trait_hint = f"你的性格特点：{character_traits}\n" if character_traits else ""

        prompt = (
            "你是一个记忆管理助手，负责记录对话中值得记住的信息。\n\n"
            f"{trait_hint}"
            "【信息来源权重】\n"
            "• 你自己说的关于自己的话（想法、感受、自述）→ source = \"self\"，权重最高\n"
            "• 对方说的关于你的话 → source = \"user\"，权重中等\n"
            "• 普通闲聊内容 → source = \"chat\"，权重较低\n\n"
            "【重要性分级 L0-L3】\n"
            "• L0 核心信念：你的核心性格、价值观、人生信条（永不过期）\n"
            "• L1 重要事实：你的经历、关系、关键事件（半年过期）\n"
            "• L2 一般经历：日常经历、偏好、感受（一个月过期）\n"
            "• L3 日常琐事：随口一提的琐碎信息（三天过期）\n"
            "• 明显不符合你性格的话 → worth = false\n\n"
            "【性格一致性检查】\n"
            "• 对方说了一些关于你的话，你认同吗？符合自我认知才记录\n"
            "• 自己发出的感慨、自述，通常更可信\n\n"
        )
        if existing:
            prompt += (
                f"【已有相关记忆】\n{existing}\n\n"
                "检查是否有重复/矛盾。\n"
                "• 重复（一模一样的内容）→ relation = duplicate\n"
                "• 覆盖（更新/更正了旧信息）→ relation = supersedes，supersedes_id 填旧记忆 id\n"
                "• 无关 → relation = null\n\n"
            )

        prompt += (
            "请严格按 JSON 格式输出：\n"
            '{"worth": true/false, "content": "一句话描述", "level": "L0"/"L1"/"L2"/"L3",'
            ' "source": "self"/"user"/"chat", "weight_factor": 1.0,'
            ' "emotion_intensity": 0.0-1.0, "emotion_label": "喜悦/悲伤/愤怒/平静/焦虑/惊讶/中性",'
            ' "relation": null/"duplicate"/"supersedes", "supersedes_id": null}\n\n'
            f"对话内容：\n{conversation}\n\n"
            "只输出 JSON，不要任何其他内容。"
        )
        try:
            resp = self.chat([{"role": "user", "content": prompt}])
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            data = json.loads(text)
            if data.get("level") not in ("L0", "L1", "L2", "L3"):
                data["level"] = "L3"
            if data.get("source") not in ("self", "user", "chat"):
                data["source"] = "chat"
            return data
        except Exception:
            return None
