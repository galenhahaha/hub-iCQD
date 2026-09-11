"""OpenAI 兼容的大模型适配器。

默认可连接 DeepSeek，也支持 OpenAI 或任何提供 Chat Completions 兼容接口的服务。
ResearchEngine 只依赖 LLMService 协议，因此离线测试不需要网络或密钥。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol, Sequence

from openai import AsyncOpenAI

from app.models import Section, Source

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """模型调用或模型输出解析失败。"""


class LLMService(Protocol):
    async def generate_keywords(self, topic: str, round_index: int = 0,
                                previous: Sequence[str] = ()) -> list[str]: ...

    async def summarize(self, topic: str, keyword: str,
                        results: Sequence[dict[str, str]]) -> str: ...

    async def is_sufficient(self, topic: str, sections: Sequence[dict[str, str]],
                            sources: Sequence[dict[str, str]]) -> bool: ...

    async def generate_summary(self, topic: str, sections: Sequence[dict[str, str]],
                               sources: Sequence[dict[str, str]], rounds: int) -> str: ...


def _parse_json(text: str) -> dict[str, Any]:
    """解析普通 JSON 或 ```json``` 包裹的 JSON。"""
    candidate = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start:end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError("模型未返回有效 JSON：{0}".format(exc)) from exc
    if not isinstance(value, dict):
        raise LLMError("模型 JSON 顶层必须是对象")
    return value


class OpenAICompatibleLLMService:
    """使用 Chat Completions 的真实 LLM 服务。"""

    def __init__(self, *, api_key: str, base_url: str, model: str,
                 timeout: float = 60, client: AsyncOpenAI | None = None) -> None:
        self.model = model
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    async def _complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        # 不强制 response_format，兼容 DeepSeek 等可能不支持 JSON Schema 的服务。
        if json_mode:
            kwargs["messages"][0]["content"] += "\n只输出一个合法 JSON 对象，不要输出 Markdown。"
        try:
            response = await self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content if response.choices else None
        except Exception as exc:  # noqa: BLE001 - 适配器统一转换异常
            raise LLMError("LLM 调用失败：{0}".format(exc)) from exc
        if not content or not content.strip():
            raise LLMError("LLM 返回空内容")
        return content.strip()

    async def generate_keywords(self, topic: str, round_index: int = 0,
                                previous: Sequence[str] = ()) -> list[str]:
        prompt = (
            "你是研究规划员。请为主题生成 2 个互补、适合网页搜索的中文关键词。"
            "第 {0} 轮；已有关键词为 {1}。只返回 {{\"keywords\":[\"...\"]}}。"
        ).format(round_index + 1, json.dumps(list(previous), ensure_ascii=False))
        value = _parse_json(await self._complete(prompt, topic, json_mode=True))
        keywords = value.get("keywords")
        if not isinstance(keywords, list):
            raise LLMError("关键词字段不是数组")
        result = [str(item).strip() for item in keywords if str(item).strip()]
        if not result:
            raise LLMError("模型没有生成有效关键词")
        return list(dict.fromkeys(result))[:4]

    async def summarize(self, topic: str, keyword: str,
                        results: Sequence[dict[str, str]]) -> str:
        system = (
            "你是研究助理。只根据给定搜索结果摘要写一段简洁、审慎的中文资料总结。"
            "不要编造搜索结果中没有的信息；如果证据不足，明确说明。"
        )
        user = json.dumps({"topic": topic, "keyword": keyword, "results": list(results)},
                          ensure_ascii=False)
        return await self._complete(system, user)

    async def is_sufficient(self, topic: str, sections: Sequence[dict[str, str]],
                            sources: Sequence[dict[str, str]]) -> bool:
        system = (
            "你是研究质量审查员。判断当前资料是否足以回答主题。"
            "仅输出 {\"sufficient\":true} 或 {\"sufficient\":false}。"
            "来源太少、内容重复或明显缺少关键方面时应为 false。"
        )
        user = json.dumps({"topic": topic, "sections": list(sections), "sources": list(sources)},
                          ensure_ascii=False)
        value = _parse_json(await self._complete(system, user, json_mode=True))
        sufficient = value.get("sufficient")
        if not isinstance(sufficient, bool):
            raise LLMError("sufficient 字段不是布尔值")
        return sufficient

    async def generate_summary(self, topic: str, sections: Sequence[dict[str, str]],
                               sources: Sequence[dict[str, str]], rounds: int) -> str:
        system = (
            "你是研究报告编辑。根据提供的研究段落和来源，生成 2-4 句中文摘要。"
            "不要添加材料中没有的事实，并说明这是基于当前检索范围的结论。"
        )
        user = json.dumps(
            {"topic": topic, "rounds": rounds, "sections": list(sections), "sources": list(sources)},
            ensure_ascii=False,
        )
        return await self._complete(system, user)
