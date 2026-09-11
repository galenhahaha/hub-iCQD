"""DeepSeek（OpenAI 兼容）调用：提示词约束 JSON，自行解析；空输出有限次重试。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from . import config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY or "missing",
            base_url=config.OPENAI_BASE_URL,
        )
    return _client


def _repair_llm_json(text: str) -> str:
    """Fix common LLM JSON: extra trailing text, unescaped quotes, truncated braces."""
    start = text.find("{")
    if start < 0:
        return text
    s = text[start:]
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "\\":
                out.append(ch)
                if i + 1 < n:
                    nxt = s[i + 1]
                    out.append("n" if nxt == "\n" else nxt)
                    i += 2
                else:
                    i += 1
                continue
            if ch == "\n":
                out.append("\\n")
                i += 1
                continue
            if ch == "\r":
                i += 1
                continue
            if ch == "\t":
                out.append("\\t")
                i += 1
                continue
            if ord(ch) < 32:
                i += 1
                continue
            if ch == '"':
                j = i + 1
                while j < n and s[j] in " \t\n\r":
                    j += 1
                nxt = s[j] if j < n else ""
                if nxt in ',}]:' or nxt == "":
                    out.append('"')
                    in_str = False
                else:
                    out.append('\\"')
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "{":
            stack.append("}")
            out.append(ch)
            i += 1
            continue
        if ch == "[":
            stack.append("]")
            out.append(ch)
            i += 1
            continue
        if ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
            out.append(ch)
            i += 1
            if not stack:
                break
            continue
        out.append(ch)
        i += 1
    result = "".join(out)
    if in_str:
        result += '"'
    result = re.sub(r",\s*([}\]])", r"\1", result)
    result = re.sub(r",\s*$", "", result.rstrip())
    result += "".join(reversed(stack))
    return result


def _load_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("no json object", text, 0)
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("json root is not an object")
    return obj


def parse_json(text: str, cls: type[T]) -> T:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty llm json")

    chunks: list[str] = [raw]
    fenced = _JSON_FENCE.search(raw)
    if fenced:
        chunks.append(fenced.group(1).strip())

    seen: set[str] = set()
    errors: list[str] = []
    for chunk in chunks:
        for variant in (chunk, _repair_llm_json(chunk)):
            if not variant or variant in seen:
                continue
            seen.add(variant)
            try:
                return cls.model_validate(_load_object(variant))
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                errors.append(str(exc))
    raise ValueError("failed to parse json: " + "; ".join(errors[:3]))


def strip_code_fence(text: str) -> str:
    raw = (text or "").strip()
    m = _JSON_FENCE.search(raw)
    if m and raw.startswith("```"):
        return m.group(1).strip()
    return raw


def _message_text(message) -> str:
    """V4 默认开 thinking：content 可能为空，最终答案有时只在 reasoning_content。"""
    content = (getattr(message, "content", None) or "").strip()
    if content:
        return content
    return (getattr(message, "reasoning_content", None) or "").strip()


def _reasoning_tokens(resp) -> int:
    usage = getattr(resp, "usage", None)
    details = getattr(usage, "completion_tokens_details", None) if usage else None
    return int(getattr(details, "reasoning_tokens", 0) or 0)


async def complete(system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 2048) -> str:
    last_empty = False
    last_exc: Exception | None = None
    for attempt in range(1, config.LLM_RETRIES + 1):
        logger.info("llm call attempt=%s/%s", attempt, config.LLM_RETRIES)
        try:
            resp = await client().chat.completions.create(
                model=config.MODEL_NAME,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # 研究循环要稳定 JSON；thinking 会占满 max_tokens，导致 content 为空。
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception as exc:
            last_exc = exc
            logger.warning("llm request failed attempt=%s: %s", attempt, exc)
            await asyncio.sleep(attempt)
            continue
        choice = resp.choices[0] if resp.choices else None
        content = _message_text(choice.message) if choice else ""
        finish = getattr(choice, "finish_reason", None) if choice else None
        logger.info(
            "llm output length=%s finish=%s reasoning_tokens=%s",
            len(content),
            finish,
            _reasoning_tokens(resp),
        )
        if content:
            return content
        last_empty = True
        logger.warning("llm empty content attempt=%s finish=%s", attempt, finish)
        await asyncio.sleep(1)
    if last_empty:
        raise RuntimeError("llm returned empty content after retries")
    raise RuntimeError(f"llm request failed after retries: {last_exc}")


async def complete_json(system: str, user: str, cls: type[T], *, temperature: float = 0.2, max_tokens: int = 2048) -> T:
    last_err: Exception | None = None
    for attempt in range(1, config.LLM_RETRIES + 1):
        text = await complete(system, user, temperature=temperature, max_tokens=max_tokens)
        try:
            return parse_json(text, cls)
        except ValueError as exc:
            last_err = exc
            logger.warning("json parse failed attempt=%s: %s", attempt, exc)
            user = user + "\n\n上一次输出无法解析为 JSON，请只输出一个合法 JSON 对象，不要 markdown。"
            await asyncio.sleep(1)
    raise RuntimeError(f"llm json parse failed: {last_err}")


if __name__ == "__main__":
    class _Demo(BaseModel):
        n: int
        tags: list[str]

    class _Extract(BaseModel):
        facts: list[str]
        paragraph: str

    sample = parse_json('```json\n{"n": 1, "tags": ["a"]}\n```', _Demo)
    print("parse_json", sample)
    trailing = parse_json('{"n": 1, "tags": ["a"]}\n{"n": 2, "tags": ["x"]}', _Demo)
    assert trailing.n == 1
    print("trailing extra ok")
    inner = parse_json(
        '{"facts":["Claude Code 的 "Agent" 能力"],"paragraph":"助或直接生成。"}',
        _Extract,
    )
    assert "Agent" in inner.facts[0]
    print("inner quotes ok", inner.facts[0])
    truncated = parse_json('{"facts":["a"],"paragraph":"hello', _Extract)
    assert truncated.paragraph.startswith("hello")
    print("truncated ok", truncated)
    try:
        parse_json("", _Demo)
    except ValueError:
        print("empty rejected")

    class _Msg:
        content = ""
        reasoning_content = '{"n": 2, "tags": ["b"]}'

    print("fallback", _message_text(_Msg()))
