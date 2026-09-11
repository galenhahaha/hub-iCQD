"""判断：是否足够写报告，不足则给出补检词。"""

from ..models import Source
from .common import JSON_RULE, as_of_rule


def system(as_of: str) -> str:
    year = (as_of or "")[:4]
    return (
        "你是研究评审。根据已有草稿和来源，判断是否足够写一份带来源的研究报告。"
        f"{as_of_rule(as_of)}"
        "禁止因为已经搜过一轮就说足够：要看是否覆盖主题的主要子问题、来源是否足够、关键事实是否仍缺。"
        f"时效上：先确认是否已尝试 {year} / 最新；若最新窗口没有结果，用更早来源也可以写报告，但要在理由里说明时效。"
        "不要因为草稿主要来自更早年份就直接判不足。"
        "若不足，给出尚未检索过的新关键词。"
        f"extra_keywords 必须是可检索短词（不超过 30 字）。优先带 {year} 或「最新」；"
        f"若这些词已经搜过且命中很少，可以改用 {int(year) - 1 if year.isdigit() else '上一年'} 或去掉年份。"
        "禁止把缺口说明整句拿去搜。"
        f"{JSON_RULE}"
        '格式：{"sufficient":true,"reason":"...","missing":["缺口"],"extra_keywords":["新词"]}'
        "sufficient 为 true 时 extra_keywords 必须是空数组。"
        "sufficient 为 false 时 extra_keywords 给 2 到 4 个新检索词，且不能与已检索词重复。"
        "missing 只写缺口，不要复制进 extra_keywords。"
    )


def user(
    topic: str,
    draft: str,
    sources: list[Source],
    searched: list[str],
    round_no: int,
    max_rounds: int,
    as_of: str,
) -> str:
    src_lines = [
        f"- {s.id}: {s.title} [{s.published or '无日期'}] ({s.url})" for s in sources[:40]
    ] or ["（暂无来源）"]
    return (
        f"今天：{as_of}\n"
        f"主题：{topic}\n"
        f"当前轮次：{round_no}/{max_rounds}\n"
        f"已检索关键词：{', '.join(searched) or '无'}\n"
        f"来源数：{len(sources)}（下列优先列出较新来源）\n"
        f"来源列表：\n" + "\n".join(src_lines) + "\n\n"
        f"当前草稿：\n{draft or '（空）'}"
    )
