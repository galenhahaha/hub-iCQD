"""第二轮独立验收新增的补覆盖测试（仅新增，不改动既有断言）。

对应主规格（openspec/specs/）中此前没有测试或断言未真正覆盖的 Scenario：

- research-engine `流程按固定顺序执行职责`（S5.1）——此前无任何测试断言职责调用顺序；
- research-engine `资料充分时只执行一轮`（S7.1）——此前只断言 rounds==1，
  未断言"不执行第二轮检索"；
- research-engine `资料不足时执行补充检索`（S7.2）——此前只断言 rounds==2，
  未断言第二轮关键词确实被检索；
- research-engine `检索返回空结果`（S9.2）——此前只有"全部关键词为空"的用例，
  缺少"某个关键词为空、其余正常"的混合用例；
- research-api `全部检索无结果`（S3.1）——此前只断言 summary 非空，
  未断言 summary 确实"说明资料不足"；
- research-api `研究接口生成研究报告`（R1）——此前 API 层测试均注入替身，
  缺少"默认装配（无 dependency_overrides）"的端到端用例。
"""

import asyncio
from typing import List, Optional, Sequence, Set

from fastapi.testclient import TestClient

from app.engine import ResearchEngine
from app.main import app
from app.models import SearchResult
from app.services import MockSearchService, SearchError


class _RecordingStub:
    """记录检索调用的桩；可按关键词返回结果或抛错。"""

    def __init__(self, results_fn, fail_for: Sequence[str] = ()) -> None:
        self.calls: List[str] = []
        self._results_fn = results_fn
        self.fail_for: Set[str] = set(fail_for)

    async def search(self, keyword: str) -> List[SearchResult]:
        self.calls.append(keyword)
        if keyword in self.fail_for:
            raise SearchError("stub failure for {0!r}".format(keyword))
        return list(self._results_fn(keyword))


class _OrderRecordingEngine(ResearchEngine):
    """记录四项职责调用顺序的引擎子类（不改 app/ 实现）。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.events: List[tuple] = []

    def generate_keywords(self, topic, round_index=0, previous=None):
        self.events.append(("generate_keywords", round_index))
        return super().generate_keywords(topic, round_index, previous)

    def summarize(self, keyword, results):
        self.events.append(("summarize", keyword))
        return super().summarize(keyword, results)

    def is_sufficient(self, sections, sources):
        self.events.append(("is_sufficient",))
        return super().is_sufficient(sections, sources)


def _result(title: str, url: str) -> SearchResult:
    return SearchResult(title=title, url=url)


# --------------------------------------------------------------------------- #
# research-engine S5.1 流程按固定顺序执行职责
# --------------------------------------------------------------------------- #
def test_responsibilities_are_called_in_required_order():
    """四项职责必须按"生成关键词 → 检索 → 汇总 → 判断充分性"的固定顺序调用。

    断言的是两种读法都成立的最小序关系：
    - generate_keywords 先于任何 search；
    - 每个关键词的 search 先于其 summarize；
    - 全部 search/summarize 先于本轮 is_sufficient。
    """
    search_events: List[tuple] = []

    class Stub:
        async def search(self, keyword: str) -> List[SearchResult]:
            search_events.append(("search", keyword))
            return [_result("资料", "https://example.com/{0}".format(keyword))]

    engine = _OrderRecordingEngine(Stub(), sufficiency_threshold=99)  # 强制两轮
    asyncio.run(engine.run("主题"))

    events = engine.events
    # 检索事件需要与职责事件合并后再判序
    merged: List[tuple] = []
    search_iter = iter(search_events)
    for event in events:
        if event[0] == "summarize":
            # 该关键词的 search 必须已发生且紧接其前
            merged.append(next(search_iter))
        merged.append(event)
    # 补齐可能剩余的 search（本用例中每个关键词都有 summarize）
    merged.extend(search_iter)

    # 按 generate_keywords 切分轮次；每轮内部验证四项职责的固定顺序
    rounds: List[List[tuple]] = []
    for event in merged:
        if event[0] == "generate_keywords":
            rounds.append([])
        assert rounds, "任何职责调用之前必须先生成关键词"
        rounds[-1].append(event)

    assert len(rounds) == 2, "本用例强制两轮，实际为 {0} 轮".format(len(rounds))
    for round_events in rounds:
        kinds = [event[0] for event in round_events]
        assert kinds[0] == "generate_keywords", "每轮必须先生成关键词"
        assert kinds[-1] == "is_sufficient", (
            "每轮必须以充分性判断收尾，实际顺序为 {0}".format(kinds)
        )
        assert kinds.count("is_sufficient") == 1, "每轮恰好一次充分性判断"
        assert kinds.index("is_sufficient") == len(kinds) - 1
        for i, event in enumerate(round_events):
            if event[0] == "summarize":
                prev = round_events[i - 1]
                assert prev[0] == "search" and prev[1] == event[1], (
                    "关键词 {0!r} 必须先检索再汇总，实际前一步为 {1!r}".format(event[1], prev)
                )

    # 判断充分性必须发生在本轮全部检索与汇总之后（而不是首个关键词之后）
    for round_events in rounds:
        judged_at = [i for i, e in enumerate(round_events) if e[0] == "is_sufficient"][0]
        assert all(
            e[0] in ("search", "summarize") for e in round_events[1:judged_at]
        ), "充分性判断前只允许出现检索与汇总"

    # S5.2 职责顺序按轮组织而非分阶段：第一轮的充分性判断必须发生在第二轮
    # 任何检索之前；第二轮先重新生成关键词，再执行该轮的检索与汇总。
    first_judgement = next(
        i for i, event in enumerate(merged) if event[0] == "is_sufficient"
    )
    round_two_start = next(
        i for i, event in enumerate(merged)
        if event[0] == "generate_keywords" and event[1] == 1
    )
    assert first_judgement < round_two_start, (
        "第一轮充分性判断必须发生在第二轮任何检索之前（第二轮以 generate_keywords 起始）"
    )
    round_two_kinds = [event[0] for event in rounds[1]]
    assert round_two_kinds[0] == "generate_keywords", "第二轮必须先重新生成关键词"
    assert "search" in round_two_kinds and "summarize" in round_two_kinds, (
        "第二轮必须执行该轮的检索与汇总"
    )


# --------------------------------------------------------------------------- #
# research-engine S7.1 / S7.2 两轮语义（"不执行第二轮检索" / 第二轮确实检索）
# --------------------------------------------------------------------------- #
def test_sufficient_round_one_does_not_search_second_round():
    """S7.1：资料充分时 rounds==1，且第二轮关键词不得被检索。"""

    def results_fn(keyword: str) -> List[SearchResult]:
        return [
            _result("资料A", "https://example.com/{0}".format(keyword)),
            _result("资料B", "https://example.com/shared"),
        ]

    service = _RecordingStub(results_fn)
    engine = ResearchEngine(service)

    response = asyncio.run(engine.run("主题"))

    assert response.process.rounds == 1
    assert service.calls == ["主题", "主题 对比"], (
        "充分时不得执行第二轮检索，实际检索调用为 {0!r}".format(service.calls)
    )
    assert not any("深入" in keyword for keyword in service.calls), (
        "第二轮派生关键词不得出现在检索调用中"
    )


def test_insufficient_round_one_actually_searches_round_two_keywords():
    """S7.2：资料不足时 rounds==2，且第二轮关键词确实被检索。"""

    def results_fn(keyword: str) -> List[SearchResult]:
        # 所有关键词返回同一 URL -> 去重后仅 1 条来源 -> 始终不充分
        return [_result("资料", "https://example.com/same")]

    service = _RecordingStub(results_fn)
    engine = ResearchEngine(service)

    response = asyncio.run(engine.run("主题"))

    assert response.process.rounds == 2
    round_two_keywords = response.process.rounds_detail[1].keywords
    assert round_two_keywords, "第二轮必须有关键词"
    for keyword in round_two_keywords:
        assert keyword in service.calls, (
            "第二轮关键词 {0!r} 必须实际被检索，实际调用 {1!r}".format(keyword, service.calls)
        )


# --------------------------------------------------------------------------- #
# research-engine S9.2 单关键词空结果
# --------------------------------------------------------------------------- #
def test_single_keyword_empty_result_produces_no_section_but_flow_continues():
    """S9.2：某个关键词返回空结果时不产生 sections 条目，其余关键词不受影响。"""
    empty_keyword = "主题"

    def results_fn(keyword: str) -> List[SearchResult]:
        if keyword == empty_keyword:
            return []
        return [_result("资料", "https://example.com/ok")]

    service = _RecordingStub(results_fn)
    engine = ResearchEngine(service)

    response = asyncio.run(engine.run("主题"))

    assert empty_keyword in service.calls, "空结果关键词仍应被检索（不是被跳过）"
    section_keywords = [section.keyword for section in response.sections]
    assert empty_keyword not in section_keywords, "空结果关键词不得产生 sections 条目"
    assert section_keywords, "其余关键词的汇总结果仍应出现在 sections 中"
    assert response.process.rounds in (1, 2), "流程正常结束"


# --------------------------------------------------------------------------- #
# research-api S3.1 summary 必须"说明资料不足"
# --------------------------------------------------------------------------- #
def test_all_empty_results_summary_explains_insufficient_material():
    """S3.1：全部检索无结果时 summary 为非空字符串，且必须说明资料不足。"""

    def results_fn(keyword: str) -> List[SearchResult]:
        return []

    service = _RecordingStub(results_fn)
    client = TestClient(app)
    app.dependency_overrides.clear()
    try:
        from app.main import get_search_service

        app.dependency_overrides[get_search_service] = lambda: service
        response = client.post("/api/research", json={"topic": "主题"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["sections"] == []
    assert body["sources"] == []
    summary = body["summary"]
    assert isinstance(summary, str) and summary.strip()
    assert "资料不足" in summary, (
        "summary 必须说明资料不足，实际为 {0!r}".format(summary)
    )


# --------------------------------------------------------------------------- #
# research-api R1 默认装配端到端（不注入任何替身）
# --------------------------------------------------------------------------- #
def test_default_wiring_returns_full_report_without_overrides():
    """默认装配（真实 MockSearchService）也能产出结构完整的报告。"""
    app.dependency_overrides.clear()
    client = TestClient(app)

    response = client.post("/api/research", json={"topic": "主流 Agent 框架对比"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"topic", "summary", "sections", "sources", "process"}
    assert body["topic"] == "主流 Agent 框架对比"
    assert body["summary"].strip()
    assert body["sections"], "默认装配下应产出 sections"
    assert body["sources"], "默认装配下应产出 sources"
    urls = [item["url"] for item in body["sources"]]
    assert len(urls) == len(set(urls)), "sources 中不得出现重复 URL"
    assert isinstance(body["process"]["keywords"], list)
    assert isinstance(body["process"]["rounds"], int)
    assert 1 <= body["process"]["rounds"] <= 2


def test_default_search_service_is_mock_implementation():
    """默认装配注入的检索实现应为本地确定性 MockSearchService。"""
    from app.main import get_search_service

    app.dependency_overrides.clear()
    service = get_search_service()
    assert isinstance(service, MockSearchService)
