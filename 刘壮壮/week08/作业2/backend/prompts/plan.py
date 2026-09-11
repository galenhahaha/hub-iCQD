"""规划：拆子问题与检索词。"""

from .common import JSON_RULE, as_of_rule


def system(as_of: str) -> str:
    year = (as_of or "")[:4]
    return (
        "你是调研规划助手。把研究主题拆成可检索的子问题和搜索关键词。"
        f"{as_of_rule(as_of)}"
        "关键词要具体、互不重复，覆盖不同角度，方便网页搜索。"
        f"首轮关键词优先锚定 {year} / 最新；不要一上来就只用更早年份。"
        "竞品、盘点、市面对比类主题：至少一条关键词要点名当前仍在更新的主流产品"
        "（不要只搜笼统的「XX工具对比 某年」）。"
        "关键词必须是可直接搜索的短词，每条不超过 30 字，禁止写成缺口说明长句。"
        f"{JSON_RULE}"
        '格式：{"sub_questions":["..."],"keywords":["..."]}'
        "sub_questions 3 到 6 条；keywords 3 到 5 条。"
    )


def user(topic: str, as_of: str) -> str:
    year = (as_of or "")[:4]
    return (
        f"今天：{as_of}\n"
        f"研究主题：{topic}\n"
        f"请从 {year} 年当下出发规划首轮检索：先覆盖当前最新信息；"
        "若最新可能不足，子问题里可以预留回溯更早资料的角度，但首轮关键词仍以当前年份为主。"
    )
