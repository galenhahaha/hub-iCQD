"""综合：结构化研究报告。"""

from ..models import Source
from .common import JSON_RULE, as_of_rule


def system(as_of: str) -> str:
    return (
        "你是研究报告撰稿人。综合草稿与来源，产出结构化报告。"
        f"{as_of_rule(as_of)}"
        "结论优先采用更新的来源；同一事实冲突时用发布时间更近的。"
        "若只有更早来源能支撑某条结论，可以采用，但必须在正文或结论里标明该来源时间，不要写成今天的新事实。"
        "标题和摘要应写明信息截止时间。"
        "每条关键结论必须带 source_ids（来源编号如 S1）。"
        "没有任何来源支撑的结论：source_ids 为空数组，inferred 必须为 true。"
        "禁止编造 URL。只能使用给定来源编号。"
        "正文分节应覆盖草稿要点，heading 简洁，body 为中文段落。"
        f"{JSON_RULE}"
        "格式："
        '{"title":"...","summary":"...","sections":[{"heading":"...","body":"...","source_ids":["S1"]}],'
        '"key_conclusions":[{"text":"...","source_ids":["S1"],"inferred":false}],'
        '"open_questions":["..."],"confidence_level":"high|medium|low","confidence_rationale":"..."}'
    )


def user(topic: str, draft: str, sources: list[Source], as_of: str) -> str:
    src_lines = []
    for s in sources:
        src_lines.append(
            f"{s.id} | {s.title} | {s.site_name} | {s.published or '无日期'} | {s.url}\n摘要：{s.snippet}"
        )
    return (
        f"今天 / 信息截止：{as_of}\n"
        f"主题：{topic}\n\n"
        f"来源：\n{(chr(10)+chr(10)).join(src_lines) or '（无来源）'}\n\n"
        f"研究草稿：\n{draft or '（空）'}"
    )
