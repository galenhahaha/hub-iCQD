# -*- coding: utf-8 -*-
"""BaseAgent：角色 agent 的基类。

封装 OpenAI Agents SDK 的全局初始化、Jinja2 提示词渲染、空输出重试、JSON 解析。
所有角色 agent（keyword/summary/judge/report）继承本类，都是无工具的单次 LLM 调用。
"""
from __future__ import annotations

import asyncio
import logging
import re

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
from jinja2 import Environment, FileSystemLoader

from .. import config

logger = logging.getLogger(__name__)

# SDK 全局初始化（模块级，只需一次）
set_default_openai_api("chat_completions")
set_tracing_disabled(True)

_templates = Environment(loader=FileSystemLoader(config.TEMPLATE_DIR), autoescape=False)


def _extract_fence(text: str) -> str | None:
    """从模型输出里抠出 JSON：优先 ```json 代码块，回退到首个 { ... } 段。"""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else None


def parse_json(text: str, output_cls):
    """把模型输出解析成指定 pydantic 模型：pydantic 直接解析 + ```json``` 代码块正则兜底。"""
    candidates = []
    fence = _extract_fence(text)
    if fence:
        candidates.append(fence)
    candidates.append(text)
    for cand in candidates:
        if not cand:
            continue
        try:
            return output_cls.model_validate_json(cand)
        except Exception:
            continue
    raise ValueError(f"无法把模型输出解析为 {output_cls.__name__}: {text[:200]!r}")


def strip_fence(text: str) -> str:
    """去掉可能的 ``` 代码块包裹（SummaryAgent / HTML 的纯文字输出兜底用）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class BaseAgent:
    """角色 agent 基类：提示词从 templates/ 渲染，单次 LLM 调用。"""

    def __init__(self, name: str, template: str):
        self.name = name
        self.template = _templates.get_template(template)

    def _render(self, **vars) -> str:
        return self.template.render(**vars)

    async def _run(self, system: str, user: str) -> str:
        """一次 LLM 调用；空输出退避 1s 重试 LLM_RETRIES 次。"""
        logger.info("[%s] 发起 LLM 调用", self.name)
        for attempt in range(1, config.LLM_RETRIES + 1):
            agent = Agent(name=self.name, instructions=system, model=config.MODEL_NAME)
            result = await Runner.run(agent, user)
            text = (result.final_output or "").strip()
            logger.debug("[%s] 第 %d 次输出长度=%d", self.name, attempt, len(text))
            if text:
                return text
            logger.warning("[%s] 第 %d/%d 次返回空输出，退避 1s 重试", self.name, attempt, config.LLM_RETRIES)
            await asyncio.sleep(1.0)
        return ""

    async def run_text(self, system_vars: dict, user_input: str) -> str:
        """渲染 system 提示词后发起调用，返回原始文本。"""
        system = self._render(**system_vars)
        return await self._run(system, user_input)

    async def call_json(self, system_vars: dict, user_input: str, output_cls):
        """结构化 JSON 输出：渲染 system -> 调用 -> parse_json 解析。"""
        text = await self.run_text(system_vars, user_input)
        return parse_json(text, output_cls)


if __name__ == "__main__":
    # 自检 demo：parse_json 兜底 + 模板渲染（纯本地，不联网）
    from ..models import KeywordOutput

    print("parse_json 直接解析:", parse_json('{"keywords": ["a", "b"]}', KeywordOutput).keywords)
    print("parse_json 代码块兜底:", parse_json('```json\n{"keywords": ["c"]}\n```', KeywordOutput).keywords)
    print("strip_fence:", repr(strip_fence("```\n正文\n```")))
    print("agent.base 自检 OK")
