"""报告 / 来源列表 / 研究过程记录 的 markdown 渲染。"""
from __future__ import annotations

from state import ResearchState


def compact_evidence(evidence: list[dict], max_items: int = 24, claim_chars: int = 180) -> list[dict]:
    """压缩证据：按来源 URL 去重、限制条数、截断 claim，避免送入 LLM 的输入过长。"""
    seen: set[str] = set()
    out: list[dict] = []
    for e in evidence:
        url = e.get("source_url", "")
        if url and url in seen:
            continue
        seen.add(url)
        e2 = dict(e)
        e2["claim"] = (e.get("claim") or "")[:claim_chars]
        out.append(e2)
        if len(out) >= max_items:
            break
    return out


def build_sources(state: ResearchState) -> list[dict]:
    """从已读页面生成唯一编号来源列表（确定性），保证报告引用编号稳定。"""
    sources: list[dict] = []
    seen: set[str] = set()
    for p in state.get("pages_read", []):
        url = p.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append({
            "source_id": len(sources) + 1,
            "title": p.get("title", ""),
            "url": url,
            "site_name": p.get("site_name", ""),
            "date": p.get("date", ""),
        })
    return sources


def _confidence_label(c: str) -> str:
    return {
        "high": "高置信",
        "medium": "中置信",
        "low": "低置信",
        "inference": "模型推断",
    }.get(c, c)


def render_sources(state: ResearchState) -> str:
    sources = state.get("sources") or build_sources(state)
    lines = ["# 来源列表", ""]
    if not sources:
        lines.append("（暂无来源）")
        return "\n".join(lines)
    for s in sources:
        date = s.get("date", "")
        lines.append(
            f"[{s['source_id']}] {s.get('title','')} —— {s.get('site_name','')} "
            f"—— {s.get('url','')}" + (f" —— {date}" if date else "")
        )
    return "\n".join(lines)


def render_process(state: ResearchState) -> str:
    lines = ["# 研究过程记录", ""]
    lines.append(f"## 研究主题\n{state.get('topic','')}\n")
    lines.append("## 规划（Planner）\n子问题：")
    for i, sq in enumerate(state.get("sub_questions", []), 1):
        lines.append(f"{i}. {sq}")
    lines.append("\n## 检索记录")
    for r in state.get("rounds", []):
        lines.append(f"- 第 {r['round']} 轮：关键词 {r['keywords']!r}")
    lines.append("\n## 已读页面")
    for i, p in enumerate(state.get("pages_read", []), 1):
        date = f"（{p.get('date','')}）" if p.get("date") else ""
        lines.append(f"- [{i}] {p.get('title','')} —— {p.get('url','')}{date}")
    lines.append("\n## 迭代轮数")
    lines.append(
        f"共 {len(state.get('rounds', []))} 轮检索，阅读 {len(state.get('pages_read', []))} 个页面，"
        f"抽取 {len(state.get('evidence', []))} 条证据。"
    )
    return "\n".join(lines)


def render_report(state: ResearchState) -> str:
    report_md = state.get("report") or ""
    lines = [f"# {state.get('topic','')} 研究报告", ""]
    lines.append(report_md.strip())
    lines.append("")
    lines.append("## 来源列表")
    for s in state.get("sources") or build_sources(state):
        lines.append(f"[{s['source_id']}] {s.get('title','')} —— {s.get('url','')}")
    return "\n".join(lines)
