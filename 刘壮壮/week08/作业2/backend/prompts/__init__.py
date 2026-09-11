"""提示词与代码分离：规划 / 抽取 / 判断 / 综合 各一份。"""

from . import extract, judge, plan, report


def plan_system(as_of: str) -> str:
    return plan.system(as_of)


def plan_user(topic: str, as_of: str) -> str:
    return plan.user(topic, as_of)


def extract_system(as_of: str) -> str:
    return extract.system(as_of)


def extract_user(topic: str, keyword: str, hits: list[dict[str, str]], as_of: str) -> str:
    return extract.user(topic, keyword, hits, as_of)


def judge_system(as_of: str) -> str:
    return judge.system(as_of)


def judge_user(
    topic: str,
    draft: str,
    sources,
    searched: list[str],
    round_no: int,
    max_rounds: int,
    as_of: str,
) -> str:
    return judge.user(topic, draft, sources, searched, round_no, max_rounds, as_of)


def report_system(as_of: str) -> str:
    return report.system(as_of)


def report_user(topic: str, draft: str, sources, as_of: str) -> str:
    return report.user(topic, draft, sources, as_of)
