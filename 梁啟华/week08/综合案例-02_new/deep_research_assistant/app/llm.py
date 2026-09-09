"""
LLM 客户端（OpenAI Chat Completions 兼容协议）
============================================
用 httpx 直连 /chat/completions，不依赖某一家厂商的 SDK，
因此 DeepSeek / OpenAI / 豆包 / 通义千问 等任何兼容服务都可以接入，
只需配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 三个环境变量即可。

设计要点：
- chat_json()：强制模型输出“JSON 对象”，供 规划 / 补检判断 / 综合 等结构化环节复用；
- JSON 解析做了多层容错：自动剥离 ```json 代码围栏、截取首尾花括号、失败抛错。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings


class LLMNotConfiguredError(RuntimeError):
    """未配置可用 LLM 时抛出，由引擎据此降级为“离线模式”。"""


class LLMError(RuntimeError):
    """LLM 请求或解析本身的错误。"""


class LLMClient:
    """最小的 OpenAI 兼容异步客户端。"""

    def __init__(self, settings: Settings) -> None:
        self._cfg = settings
        # 复用同一个 httpx 客户端，启用连接池、避免每次请求重复建连
        self._http = httpx.AsyncClient(
            timeout=settings.llm_timeout,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """是否具备调用条件。"""
        return self._cfg.llm_available

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """通用对话补全，返回纯文本回复。"""
        if not self.available:
            raise LLMNotConfiguredError("未配置 LLM_API_KEY，当前为离线模式。")

        payload: Dict[str, Any] = {
            "model": self._cfg.llm_model,
            "messages": messages,
            "temperature": self._cfg.llm_temperature if temperature is None else temperature,
            "max_tokens": self._cfg.llm_max_tokens if max_tokens is None else max_tokens,
        }
        data = await self._post(payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"LLM 响应结构异常：{data}") from exc

    async def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        """要求模型输出一个 JSON 对象并解析为 dict。

        说明：并非所有兼容网关都硬性支持 response_format，
        这里用“提示词要求 + 客户端容错解析”双保险，兼容性最好。
        """
        text = await self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,  # 结构化输出压低随机性，保证稳定性
        )
        return self._parse_json(text)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    async def _post(self, payload: Dict[str, Any], retries: int = 2) -> Dict[str, Any]:
        """POST /chat/completions，对 5xx/网络错误做少量重试。"""
        url = self._cfg.llm_base_url.rstrip("/") + "/chat/completions"
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = await self._http.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # 4xx（如鉴权失败/余额不足）重试无意义，直接中断；仅 5xx 继续重试
                if exc.response.status_code < 500:
                    break
            except httpx.HTTPError as exc:
                last_exc = exc
            if attempt < retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise LLMError(f"LLM 请求失败（{url}）：{last_exc}")

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """从模型回复中稳健抽取 JSON 对象。"""
        if not text or not text.strip():
            raise LLMError("模型返回了空内容")
        cleaned = text.strip()
        # 1) 剥离 ```json ... ``` 代码围栏
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        # 2) 只截取第一对 { } 之间的内容，防模型在 JSON 前后写解释文字
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
        # 3) 真正解析
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMError(f"无法解析模型返回的 JSON：{text[:200]}…") from exc
        if not isinstance(parsed, dict):
            raise LLMError(f"模型返回的不是 JSON 对象：{parsed!r}")
        return parsed

    async def aclose(self) -> None:
        """进程退出时关闭底层连接池。"""
        await self._http.aclose()
