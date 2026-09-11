"""
应用配置模块
============
集中管理所有可通过「环境变量 / .env 文件」覆盖的配置项，
避免在业务代码里散落魔法字符串。

配置来源优先级：环境变量 > .env 文件 > 代码默认值
（本模块 import 时自动尝试加载项目根目录的 .env）
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# 可选加载 .env；若未安装 python-dotenv 或文件不存在，静默跳过
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover —— 容错处理，保证缺依赖也能启动
    pass


def _get(name: str, default: str = "") -> str:
    """读取字符串型环境变量；值为空串时统一视为「未设置」。"""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_int(name: str, default: int) -> int:
    """读取整型环境变量；缺失或解析失败时回退到默认值。"""
    try:
        return int(_get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """只读配置对象，进程内实例化一次后全局复用。"""

    # ---------- 应用基础信息 ----------
    app_name: str = "Deep Research Assistant"
    version: str = "0.1.0"
    host: str = _get("HOST", "127.0.0.1")
    port: int = _get_int("PORT", 8000)
    debug: bool = _get("DEBUG", "0") in ("1", "true", "True", "yes")

    # ---------- Bocha 网页搜索 ----------
    # 文档：https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
    bocha_api_key: str = _get(
        "BOCHA_API_KEY",
        # 默认使用课程文档给出的示例 Key，方便开箱即用；建议替换为自己申请的 Key
        "sk-3d2293ad83aa4823a7c7ce8dd5ff8c72",
    )
    bocha_url: str = _get("BOCHA_URL", "https://api.bocha.cn/v1/web-search")
    bocha_timeout: float = float(_get("BOCHA_TIMEOUT", "15"))

    # ---------- LLM（兼容 OpenAI Chat Completions 协议即可）----------
    # 默认指向 DeepSeek；接入 OpenAI / 豆包 / 通义 / 月之暗面等只需改下面三项
    llm_api_key: str = _get("LLM_API_KEY", "")
    llm_base_url: str = _get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_model: str = _get("LLM_MODEL", "deepseek-chat")
    llm_timeout: float = float(_get("LLM_TIMEOUT", "90"))
    llm_max_tokens: int = _get_int("LLM_MAX_TOKENS", 4000)
    llm_temperature: float = float(_get("LLM_TEMPERATURE", "0.3"))

    # ---------- 研究流程参数 ----------
    max_rounds: int = _get_int("MAX_ROUNDS", 1)          # 初始检索之外的“智能补检”轮次数
    results_per_query: int = _get_int("RESULTS_PER_QUERY", 5)  # 每个关键词取几条结果
    max_pages_to_read: int = _get_int("MAX_PAGES_TO_READ", 8)  # “真实阅读”网页正文的上限
    page_fetch_timeout: float = float(_get("PAGE_FETCH_TIMEOUT", "8"))  # 单页抓取超时秒
    page_text_max_chars: int = _get_int("PAGE_TEXT_MAX_CHARS", 2500)    # 单页正文截断字符数
    max_sources_total: int = _get_int("MAX_SOURCES_TOTAL", 25)          # 报告保留来源上限

    # ---------- 任务 / 生命周期 ----------
    task_ttl_seconds: int = _get_int("TASK_TTL_SECONDS", 3600)  # 已完成任务内存保留时长

    # ---------- 派生属性 ----------
    @property
    def llm_available(self) -> bool:
        """是否已配置可用 LLM：三项缺一不可。"""
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def research_mode(self) -> str:
        """研究模式：full=完整(LLM 深度综合)；offline=离线(仅检索拼装基础报告)。"""
        return "full" if self.llm_available else "offline"
