"""Shared prompt rendering, async model calls, and JSON validation."""

import asyncio
import logging
import re
from typing import Any, TypeVar

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    set_default_openai_api,
    set_tracing_disabled,
)
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .. import config


set_default_openai_api("chat_completions")
set_tracing_disabled(True)

BASE_MODEL = config.MODEL_NAME
logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_env = Environment(
    loader=FileSystemLoader(str(config.TEMPLATE_DIR)),
    undefined=StrictUndefined,
    autoescape=False,  # These templates produce prompts, not HTML pages.
    keep_trailing_newline=True,
)
_JSON_FENCE = re.compile(r"```(?:json\b)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def parse_json(text: str, output_cls: type[T]) -> T:
    """Validate raw JSON first, then try JSON or unlabelled fenced blocks."""
    try:
        return output_cls.model_validate_json(text)
    except ValidationError as exc:
        last_error = exc

    for match in _JSON_FENCE.finditer(text):
        try:
            return output_cls.model_validate_json(match.group(1).strip())
        except ValidationError as exc:
            last_error = exc

    # Report field locations without logging the potentially sensitive output.
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
        for error in last_error.errors(include_input=False)[:3]
    )
    raise ValueError(f"无法解析 {output_cls.__name__}：{details}") from last_error


class BaseAgent:
    """A tool-free role with one model turn per attempt."""

    agent_name = "BaseAgent"
    template_name = ""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or BASE_MODEL

    def _render(self, template_name: str | None = None, **variables: Any) -> str:
        return _env.get_template(template_name or self.template_name).render(**variables)

    async def _run(
        self,
        system_vars: dict[str, Any],
        user_input: str,
        template_name: str | None = None,
    ) -> str:
        """Return raw text; retry empty responses after a one-second delay."""
        instructions = self._render(template_name, **system_vars)
        if not config.OPENAI_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置，请设置进程环境变量（兼容 OPENAI_API_KEY）。")
        if config.LLM_RETRIES < 0:
            raise ValueError("LLM_RETRIES 不能小于 0。")

        # Create the client only when called; importing roles needs no API key.
        async with AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        ) as client:
            agent = Agent(
                name=self.agent_name,
                instructions=instructions,
                model=OpenAIChatCompletionsModel(model=self.model, openai_client=client),
                tools=[],
            )
            # LLM_RETRIES counts additional attempts after the initial call.
            for attempt in range(config.LLM_RETRIES + 1):
                result = await Runner.run(agent, user_input, max_turns=1)
                text = result.final_output
                if isinstance(text, str) and text.strip():
                    return text
                if text is not None and not isinstance(text, str):
                    raise TypeError(f"{self.agent_name} 返回了非文本输出。")
                if attempt < config.LLM_RETRIES:
                    logger.warning(
                        "%s returned empty output; retry %d/%d in 1s",
                        self.agent_name,
                        attempt + 1,
                        config.LLM_RETRIES,
                    )
                    await asyncio.sleep(1.0)

        raise RuntimeError(
            f"{self.agent_name} 连续 {config.LLM_RETRIES + 1} 次返回空输出。"
        )

    async def call_json(
        self,
        system_vars: dict[str, Any],
        user_input: str,
        output_cls: type[T],
        template_name: str | None = None,
    ) -> T:
        text = await self._run(system_vars, user_input, template_name)
        return parse_json(text, output_cls)
