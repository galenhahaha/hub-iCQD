"""全局配置与 LLM 工厂。

通过环境变量 ``LLM_PROVIDER`` 在 Anthropic / OpenAI 两种协议间切换：

- LLM_PROVIDER          推理引擎：``anthropic``（默认）/ ``openai``
- ANTHROPIC_BASE_URL    Anthropic 兼容网关地址（默认 http://127.0.0.1:15721）
- ANTHROPIC_AUTH_TOKEN  网关鉴权 token
- ANTHROPIC_MODEL       使用的模型（默认 claude-haiku-4-5）
- OPENAI_BASE_URL       OpenAI 兼容网关地址（默认 https://api.openai.com/v1）
- OPENAI_API_KEY        OpenAI API key
- OPENAI_MODEL          使用的模型（默认 gpt-4o-mini）
- BOCHA_API_KEY         Bocha Web Search API key
"""
from __future__ import annotations

import json
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI

# —— Anthropic 兼容网关 ——
ANTHROPIC_BASE_URL = "http://127.0.0.1:15721"
ANTHROPIC_AUTH_TOKEN = "PROXY_KEY"
ANTHROPIC_MODEL = "claude-haiku-4-5"

# —— OpenAI 兼容网关 ——
OPENAI_BASE_URL = "https://api.deepseek.com"
OPENAI_API_KEY = "***" #填写你自己的api_key
OPENAI_MODEL = "deepseek-flash"

# —— 搜索工具 ——
BOCHA_API_KEY = os.environ.get(
    "BOCHA_API_KEY",
    "sk-3d2293ad83aa4823a7c7ce8dd5ff8c72",
)
BOCHA_SEARCH_URL = "https://api.bocha.cn/v1/web-search"

# —— 研究流程参数 ——
DEFAULT_MAX_ITERATIONS = 2   # 1 轮初检 + 1 轮补检
SEARCH_COUNT_PER_KEYWORD = 5 # 每个关键词返回条数
MAX_KEYWORDS_PER_ROUND = 6   # 每轮最多检索关键词数
MAX_PAGES_PER_EXTRACT = 16   # 每轮送入抽取 Agent 的最大页面数
MAX_SUMMARY_CHARS = 600      # 每条页面摘要送入 LLM 前的截断长度


def build_llm(model: str | None = None, max_tokens: int = 4096,
              thinking: bool = True) -> BaseChatModel:
    """构建 LLM，支持 Anthropic / OpenAI 两种协议（由 ``LLM_PROVIDER`` 决定）。

    ``thinking`` 控制是否开启推理模型的思考过程（默认开启，保留推理质量）：

    - 结构化抽取（Planner/Extractor/Judge）需强制 ``tool_choice``，而 thinking 模式
      拒绝强制 tool_choice（报 "Thinking mode does not support this tool_choice"），
      故这些 Agent 传 ``thinking=False``。
    - 纯文本生成（Writer）无需 tool_choice，保持 ``thinking=True`` 以保留推理质量。
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "openai":
        # thinking=False 时透传 thinking=disabled；否则不注入该字段（走端点默认=开启）。
        # 可用 OPENAI_EXTRA_BODY（JSON）完全覆盖，如 {"thinking": {"type": "enabled"}}。
        extra_body = json.loads(os.environ.get("OPENAI_EXTRA_BODY", "{}"))
        if not thinking:
            extra_body.setdefault("thinking", {"type": "disabled"})
        return ChatOpenAI(
            model=model or os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            base_url=os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL),
            api_key=os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY),
            max_tokens=max_tokens,
            timeout=120,
            max_retries=2,
            extra_body=extra_body,
        )

    # 默认 anthropic
    return ChatAnthropic(
        model=model or os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_MODEL),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ANTHROPIC_BASE_URL),
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", ANTHROPIC_AUTH_TOKEN),
        max_tokens=max_tokens,
        timeout=120,
        max_retries=2,
        thinking={"type": "disabled"} if not thinking else {"type": "enabled"},
    )


def build_structured_llm(schema, model: str | None = None, max_tokens: int = 4096):
    """构建支持结构化输出的链，thinking 保持开启。

    实现：``bind_tools(tool_choice="auto") + PydanticToolsParser``。

    为什么不直接 ``with_structured_output(method="function_calling")``？后者会发
    ``tool_choice="required"``（强制调用工具），而 DeepSeek 等推理模型在 thinking
    模式下拒绝强制 tool_choice（报 "Thinking mode does not support this tool_choice"）。
    改用 ``tool_choice="auto"`` 让模型自主决定调用，thinking 全程开启，结构化解析
    由 PydanticToolsParser 兜底。
    """
    llm = build_llm(model=model, max_tokens=max_tokens, thinking=True)
    tool_schema = convert_to_openai_tool(schema)
    chain = llm.bind_tools([tool_schema], tool_choice="auto") | PydanticToolsParser(
        tools=[schema]
    )

    class _StructuredInvoker:
        """包装链，使 ``invoke(prompt)`` 返回单个 schema 对象（而非 list）。"""

        def invoke(self, prompt: str):
            results = chain.invoke(prompt)
            if not results:
                raise RuntimeError(
                    f"结构化输出失败：模型未调用工具（{getattr(schema, '__name__', schema)}），"
                    "返回为空。可重试或检查 prompt。"
                )
            return results[0]

    return _StructuredInvoker()
