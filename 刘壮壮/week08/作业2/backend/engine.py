"""研究引擎：规划 → 检索 → 抽取 → 判断补检 → 综合。不含 LLM 角色类，只做控制流。"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import prompts, search
from .core import config, llm
from .models import (
    Confidence,
    Conclusion,
    ExtractOutput,
    JudgeOutput,
    PlanOutput,
    ProcessStep,
    Report,
    ReportOutput,
    ReportSection,
    ResearchRecord,
    ReviewedItem,
    Source,
    StepKind,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[ResearchRecord], Awaitable[None] | None]
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_YEAR_RE = re.compile(r"20\d{2}")
_TIME_WORDS = ("目前", "当前", "最新", "市面", "现在", "今年")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def _year_of(as_of: str) -> int:
    try:
        return int(as_of[:4])
    except ValueError:
        return datetime.now(LOCAL_TZ).year


def _wants_latest(topic: str, year: int) -> bool:
    """时效主题从今天往回看；主题写死过去年份则尊重原意。"""
    text = topic or ""
    if any(word in text for word in _TIME_WORDS):
        return True
    years = _YEAR_RE.findall(text)
    if years and str(year) not in years:
        return False
    return True


def _align_keyword_year(topic: str, keyword: str, year: int) -> str:
    if not _wants_latest(topic, year):
        return keyword
    cur, prev = str(year), str(year - 1)
    if prev in keyword and cur not in keyword:
        return keyword.replace(prev, cur)
    return keyword


def _ensure_current_year(topic: str, keywords: list[str], year: int) -> list[str]:
    aligned = [_align_keyword_year(topic, kw, year) for kw in keywords]
    if not aligned or not _wants_latest(topic, year):
        return aligned
    cur = str(year)
    if any(cur in kw for kw in aligned):
        return aligned
    aligned[0] = f"{aligned[0]} {cur}".strip()
    return aligned


def _parse_published(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _published_sort_value(raw: str) -> datetime:
    parsed = _parse_published(raw)
    if parsed is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _prefer_recent(hits: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(hits, key=lambda hit: _published_sort_value(hit.get("published", "")), reverse=True)


def _recent_sources(sources: list[Source], limit: int = 40) -> list[Source]:
    return sorted(sources, key=lambda src: _published_sort_value(src.published), reverse=True)[:limit]


_THIN_HITS = 2


def _strip_years(keyword: str) -> str:
    return " ".join(_YEAR_RE.sub(" ", keyword).split())


def _merge_hit_lists(primary: list[dict[str, str]], extra: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = {hit.get("url", "") for hit in primary if hit.get("url")}
    out = list(primary)
    for hit in extra:
        url = hit.get("url", "")
        if url and url not in seen:
            seen.add(url)
            out.append(hit)
    return out


def _older_keyword_variants(keyword: str, year: int) -> list[str]:
    cur = str(year)
    if cur not in keyword:
        return []
    variants: list[str] = []
    prev = keyword.replace(cur, str(year - 1))
    if prev != keyword:
        variants.append(prev)
    bare = _strip_years(keyword)
    if bare and bare.casefold() not in {keyword.casefold(), prev.casefold()}:
        variants.append(bare)
    return variants


def _search_freshness(topic: str, year: int) -> str | None:
    raw = (config.BOCHA_FRESHNESS or "auto").strip()
    if raw in {"", "auto"}:
        return "oneYear" if _wants_latest(topic, year) else None
    if raw == "noLimit":
        return None
    return raw


async def _search_hits(
    keyword: str,
    freshness: str | None,
    *,
    year: int,
    widen: bool,
) -> tuple[list[dict[str, str]], str, list[str]]:
    """先按最新窗口搜；没查到再放开时间，必要时回溯上一年。"""
    notes: list[str] = []
    widened: list[str] = []
    hits = await search.web_search(keyword, freshness=freshness)
    window = freshness or "noLimit"
    if freshness and len(hits) < _THIN_HITS:
        notes.append(f"{window} 命中 {len(hits)} 条，已放开时间")
        broader = await search.web_search(keyword, freshness="noLimit")
        hits = _merge_hit_lists(hits, broader)
        window = "noLimit"
    if widen and len(hits) < _THIN_HITS:
        for older_kw in _older_keyword_variants(keyword, year):
            older = await search.web_search(older_kw, freshness="noLimit")
            widened.append(older_kw)
            if not older:
                continue
            notes.append(f"最新命中不足，已补「{older_kw}」")
            hits = _merge_hit_lists(hits, older)
    if not notes:
        notes.append(f"时效={window}")
    return _prefer_recent(hits), "；".join(notes), widened


async def _progress(record: ResearchRecord, fn: ProgressFn | None) -> None:
    record.updated_at = _now()
    if fn is None:
        return
    result = fn(record)
    if inspect.isawaitable(result):
        await result


def _add_step(record: ResearchRecord, kind: StepKind, title: str, detail: str, round_no: int) -> None:
    record.process.steps.append(
        ProcessStep(kind=kind, round=round_no, title=title, detail=detail, at=_now())
    )


def _next_source_id(existing: list[Source]) -> str:
    return f"S{len(existing) + 1}"


def _merge_hits(record: ResearchRecord, keyword: str, hits: list[dict[str, str]]) -> list[Source]:
    by_url = {s.url: s for s in record.sources}
    added: list[Source] = []
    reviewed_urls = {item.url for item in record.process.reviewed}
    for hit in hits:
        url = hit["url"]
        title = hit["title"] or url
        if url not in reviewed_urls:
            record.process.reviewed.append(ReviewedItem(title=title, url=url, query=keyword))
            reviewed_urls.add(url)
        if url in by_url:
            continue
        src = Source(
            id=_next_source_id(record.sources),
            title=title,
            url=url,
            snippet=hit.get("snippet", ""),
            site_name=hit.get("site_name", ""),
            published=hit.get("published", ""),
        )
        record.sources.append(src)
        by_url[url] = src
        added.append(src)
    return added


def _normalize_ids(raw_ids: list[str], valid: set[str]) -> list[str]:
    out: list[str] = []
    for raw in raw_ids:
        token = str(raw).strip().upper().replace(" ", "")
        if not token:
            continue
        if token in valid:
            cand = token
        elif token.startswith("S") and token[1:].isdigit() and token in valid:
            cand = token
        elif token.isdigit() and f"S{token}" in valid:
            cand = f"S{token}"
        else:
            continue
        if cand not in out:
            out.append(cand)
    return out


def _finalize_report(raw: ReportOutput, valid_ids: set[str]) -> Report:
    sections: list[ReportSection] = []
    for sec in raw.sections:
        sections.append(
            ReportSection(
                heading=sec.heading,
                body=sec.body,
                source_ids=_normalize_ids(sec.source_ids, valid_ids),
            )
        )
    conclusions: list[Conclusion] = []
    for item in raw.key_conclusions:
        ids = _normalize_ids(item.source_ids, valid_ids)
        inferred = bool(item.inferred) or not ids
        conclusions.append(Conclusion(text=item.text, source_ids=[] if inferred else ids, inferred=inferred))
    return Report(
        title=raw.title.strip() or "研究报告",
        summary=raw.summary.strip(),
        sections=sections,
        key_conclusions=conclusions,
        open_questions=[q.strip() for q in raw.open_questions if q.strip()],
    )


def _confidence(record: ResearchRecord, rationale: str, level: str) -> Confidence:
    inferred = 0
    if record.report:
        inferred = sum(1 for c in record.report.key_conclusions if c.inferred)
    sources_n = len(record.sources)
    rounds = record.process.iterations
    if sources_n >= 8 and rounds >= 2 and inferred == 0:
        computed = "high"
    elif sources_n >= 4:
        computed = "medium"
    else:
        computed = "low"
    picked = level if level in {"high", "medium", "low"} else computed
    # 无来源时不允许标 high
    if sources_n == 0:
        picked = "low"
    return Confidence(
        level=picked,  # type: ignore[arg-type]
        as_of=_today(),
        rationale=rationale.strip() or f"来源 {sources_n} 条，迭代 {rounds} 轮，模型推断结论 {inferred} 条。",
        inferred_count=inferred,
    )


def _unique_keywords(words: list[str], seen: set[str]) -> list[str]:
    out: list[str] = []
    used = set(seen)
    for raw in words:
        key = " ".join((raw or "").split())
        if not key:
            continue
        folded = key.casefold()
        if folded in used:
            continue
        used.add(folded)
        out.append(key)
    return out


def _fallback_extract(keyword: str, hits: list[dict[str, str]]) -> ExtractOutput:
    facts: list[str] = []
    bits: list[str] = []
    for hit in hits[:8]:
        title = (hit.get("title") or "").strip()
        snippet = (hit.get("snippet") or "").strip()
        if title and title not in facts:
            facts.append(title[:80])
        if title and snippet:
            bits.append(f"{title}：{snippet}")
        elif snippet:
            bits.append(snippet)
        elif title:
            bits.append(title)
    paragraph = " ".join(bits).strip()
    if not paragraph:
        paragraph = f"关键词「{keyword}」的检索结果没有可用摘要。"
    return ExtractOutput(facts=facts[:6], paragraph=paragraph[:800])


async def run_loop(record: ResearchRecord, on_progress: ProgressFn | None = None) -> ResearchRecord:
    topic = record.topic.strip()
    max_rounds = config.RESEARCH_MAX_ROUNDS
    as_of = _today()
    year = _year_of(as_of)
    freshness = _search_freshness(topic, year)
    logger.info(
        "engine start id=%s topic=%s max_rounds=%s as_of=%s freshness=%s",
        record.id,
        topic,
        max_rounds,
        as_of,
        freshness or "noLimit",
    )

    plan = await llm.complete_json(
        prompts.plan_system(as_of),
        prompts.plan_user(topic, as_of),
        PlanOutput,
        temperature=0.2,
        max_tokens=1024,
    )
    keywords = _unique_keywords(plan.keywords or plan.sub_questions, set())
    if not keywords:
        keywords = [topic]
    keywords = _ensure_current_year(topic, keywords, year)
    record.process.iterations = 0
    _add_step(
        record,
        "plan",
        "规划子问题与检索词",
        f"信息截止：{as_of}\n子问题：" + "；".join(plan.sub_questions[:6]) + "\n关键词：" + "；".join(keywords),
        0,
    )
    await _progress(record, on_progress)

    seen: set[str] = set()
    queue = list(keywords)

    for round_no in range(1, max_rounds + 1):
        record.process.iterations = round_no
        batch = _unique_keywords(queue, seen)
        if not batch:
            _add_step(record, "judge", "没有新的检索词，结束循环", "队列为空", round_no)
            await _progress(record, on_progress)
            break

        for kw in batch:
            seen.add(kw.casefold())
            record.process.queries.append(kw)
            hits, search_note, widened = await _search_hits(
                kw,
                freshness,
                year=year,
                widen=_wants_latest(topic, year),
            )
            for extra_kw in widened:
                folded = extra_kw.casefold()
                if folded not in seen:
                    seen.add(folded)
                    record.process.queries.append(extra_kw)
            added = _merge_hits(record, kw, hits)
            _add_step(
                record,
                "search",
                f"检索「{kw}」",
                f"命中 {len(hits)} 条，新增来源 {len(added)} 条。{search_note}",
                round_no,
            )
            await _progress(record, on_progress)

            try:
                extracted = await llm.complete_json(
                    prompts.extract_system(as_of),
                    prompts.extract_user(topic, kw, hits, as_of),
                    ExtractOutput,
                    temperature=0.2,
                    max_tokens=2048,
                )
            except RuntimeError as exc:
                logger.warning("extract json failed keyword=%s, fallback snippets: %s", kw, exc)
                extracted = _fallback_extract(kw, hits)
            paragraph = extracted.paragraph.strip()
            if paragraph:
                block = f"## {kw}\n\n{paragraph}\n"
                record.draft = (record.draft + "\n" + block).strip()
            fact_n = len(extracted.facts)
            _add_step(
                record,
                "extract",
                f"抽取「{kw}」",
                (paragraph[:400] + ("…" if len(paragraph) > 400 else ""))
                or f"抽出 {fact_n} 条事实。",
                round_no,
            )
            await _progress(record, on_progress)

        judge = await llm.complete_json(
            prompts.judge_system(as_of),
            prompts.judge_user(
                topic,
                record.draft,
                _recent_sources(record.sources),
                record.process.queries,
                round_no,
                max_rounds,
                as_of,
            ),
            JudgeOutput,
            temperature=0.1,
            max_tokens=1024,
        )
        extra = [kw for kw in _unique_keywords(judge.extra_keywords, seen) if len(kw) <= 40]
        detail = judge.reason.strip()
        if judge.missing:
            detail += "\n缺口：" + "；".join(judge.missing)
        if extra:
            detail += "\n补检词：" + "；".join(extra)
        _add_step(
            record,
            "judge",
            "信息已足够，准备写报告" if judge.sufficient else "信息不足，需要补检",
            detail,
            round_no,
        )
        await _progress(record, on_progress)

        if judge.sufficient:
            logger.info("judge sufficient at round=%s", round_no)
            break
        if round_no >= max_rounds:
            logger.info("hit max rounds=%s", max_rounds)
            break
        queue = extra
        if not queue:
            logger.info("judge requested more but extra keywords empty")
            break

    raw_report = await llm.complete_json(
        prompts.report_system(as_of),
        prompts.report_user(topic, record.draft, record.sources, as_of),
        ReportOutput,
        temperature=0.2,
        max_tokens=4096,
    )
    valid = {s.id.upper() for s in record.sources}
    record.report = _finalize_report(raw_report, valid)
    record.confidence = _confidence(record, raw_report.confidence_rationale, raw_report.confidence_level)
    _add_step(
        record,
        "synthesize",
        "综合生成报告",
        f"结论 {len(record.report.key_conclusions)} 条，来源 {len(record.sources)} 条，置信度 {record.confidence.level}。",
        record.process.iterations,
    )
    await _progress(record, on_progress)
    logger.info("engine done id=%s", record.id)
    return record


if __name__ == "__main__":
    hits = _prefer_recent(
        [
            {"title": "old", "published": "2024-01-01T00:00:00+08:00"},
            {"title": "new", "published": "2026-09-01T00:00:00+08:00"},
            {"title": "none", "published": ""},
        ]
    )
    assert [h["title"] for h in hits] == ["new", "old", "none"]
    topic = "目前市面上所有 AI coding 编程工具对比"
    assert _wants_latest(topic, 2026)
    assert not _wants_latest("2024 年欧盟 AI 法案原文对照", 2026)
    assert _align_keyword_year(topic, "AI coding 工具 对比 2025", 2026) == "AI coding 工具 对比 2026"
    assert _ensure_current_year(topic, ["AI 编程助手 评测 排行"], 2026)[0].endswith("2026")
    assert _older_keyword_variants("AI coding 工具 对比 2026", 2026) == [
        "AI coding 工具 对比 2025",
        "AI coding 工具 对比",
    ]
    merged = _merge_hit_lists(
        [{"url": "https://a", "title": "new"}],
        [{"url": "https://a", "title": "dup"}, {"url": "https://b", "title": "old"}],
    )
    assert [h["url"] for h in merged] == ["https://a", "https://b"]
    assert "2026" in __import__("backend.prompts.plan", fromlist=["user"]).user(topic, "2026-09-11")
    print("ok", _today(), hits[0]["title"])
