"""各步骤共用的 JSON 输出约束。"""

JSON_RULE = (
    "只输出一个 JSON 对象，不要 markdown，不要代码块，不要解释。"
    "不要使用 json_schema / 函数调用，直接输出 JSON 文本。"
    "字符串值里不要使用英文双引号，引用请用「」。"
    "JSON 对象结束后不要再输出任何文字。"
)


def as_of_rule(as_of: str) -> str:
    year = (as_of or "")[:4] or "当年"
    prev = str(int(year) - 1) if year.isdigit() else "更早"
    return (
        f"今天是 {as_of}，当前年份是 {year}。"
        "时效主题先从今天 / 当前年份出发检索，但不要求所有材料都必须是最新："
        f"优先 {year} 与「最新」；若最新窗口没有可用结果，必须回溯更早资料（如 {prev}），"
        "采用时标明其发布时间，不要把过时材料伪装成今天的结论。"
    )
