"""
网页正文抓取与净化
==================
负责把搜索结果背后的网页原文抓下来、抽取可读的正文文本，
作为“阅读抽取”环节的输入材料。

现实约束：反爬、JS 动态渲染、各种编码与标签错乱。因此本模块全程容错——
任何一步失败都只返回 None，由上层回退到搜索引擎自带的 summary / snippet，
绝不让单个页面影响整条研究链路。
"""
from __future__ import annotations

import html as html_module
import re
from typing import Optional

import httpx

# 伪装成浏览器，绕过最简单的反爬校验
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 需要整段剔除的“噪声”标签（内容不参与阅读）
_NOISE_TAGS = ("script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "aside", "form")
# 其余标签统一替换成空格
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


async def fetch_page_text(
    url: str,
    timeout: float = 8.0,
    max_chars: int = 2500,
) -> Optional[str]:
    """抓取网页并抽取干净的正文文本。

    参数:
        url:      网页链接
        timeout:  单个页面抓取超时（秒）
        max_chars: 返回文本的最大字符数（控制 token 开销）

    返回:
        清洗后的纯文本，或抓取/解析失败时的 None
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        # 超时 / 4xx / 5xx / 反爬 / 证书异常……一律静默降级
        return None

    return _extract_text(html, max_chars)


def _extract_text(html: str, max_chars: int) -> str:
    """从 HTML 中启发式抽取正文文本。"""
    # 1) 剔除噪声标签及其内部内容
    for tag in _NOISE_TAGS:
        html = re.sub(rf"(?is)<{tag}\b[^>]*>.*?</{tag}>", " ", html)
    # 2) 去掉剩余所有标签
    text = _STRIP_TAGS_RE.sub(" ", html)
    # 3) 还原 HTML 实体，例如 &amp; -> &、&nbsp; -> 空格
    text = html_module.unescape(text)
    # 4) 规整空白：行内多空格压成一个；压缩连续空行
    text = re.sub(r"[ \t\x0c]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()
    # 5) 按需求截断（只取正文开头，兼顾信息量与 token 成本）
    return text[:max_chars]
