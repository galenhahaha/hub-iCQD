"""抽取：从搜索摘要写成草稿段落。"""

from .common import JSON_RULE, as_of_rule


def system(as_of: str) -> str:
    return (
        "你是资料抽取助手。根据搜索结果的标题、摘要、snippet 提取与主题相关的事实，"
        "写成一段可放入报告草稿的中文正文。不要编造检索结果里没有的数字或出处。"
        f"{as_of_rule(as_of)}"
        "优先采用发布时间更近的结果；若没有今年 / 最新材料，就采用更早结果，并在正文标明年份。"
        "不要把多年前的底层模型名当成当前仍在销售的独立产品。"
        "只有结果为空或完全无关时，才说明本关键词没有可用公开信息；有较早但相关的材料不要整段弃用。"
        f"{JSON_RULE}"
        '格式：{"facts":["短句事实"],"paragraph":"一段连贯正文"}'
        "facts 3 到 6 条，每条不超过 40 字；paragraph 不超过 280 字。"
    )


def user(topic: str, keyword: str, hits: list[dict[str, str]], as_of: str) -> str:
    lines = [
        f"今天：{as_of}",
        f"主题：{topic}",
        f"本轮关键词：{keyword}",
        "搜索结果（越靠前越新）：",
    ]
    if not hits:
        lines.append("（无结果）")
    for i, hit in enumerate(hits, 1):
        lines.append(
            f"[{i}] 标题：{hit.get('title','')}\n"
            f"URL：{hit.get('url','')}\n"
            f"站点：{hit.get('site_name','')}\n"
            f"时间：{hit.get('published','') or '未知'}\n"
            f"摘要：{hit.get('snippet','')}"
        )
    return "\n".join(lines)
