"""研究助手的自动化测试。

测试组织与 tasks.md 的任务一一对应：
- 2.2 / 3.1~3.5 / 4.1~4.2 的任务内即写出对应测试（TDD 顺序）；
- 5.1~5.5 对 README 第 5 节的 5 个必测场景做覆盖确认与补齐。
"""

import asyncio
import logging
from typing import Dict, List, Optional, Sequence, Set

import pytest
from fastapi.testclient import TestClient

from app.engine import MAX_ROUNDS, ResearchEngine
from app.main import app, get_engine, get_search_service
from app.models import (
    ProcessInfo,
    ResearchRequest,
    ResearchResponse,
    SearchResult,
    Section,
    Source,
)
from app.services import (
    MockSearchService,
    ResilientSearchService,
    SearchError,
    SearchService,
)


# --------------------------------------------------------------------------- #
# 测试替身
# --------------------------------------------------------------------------- #
class StubSearchService:
    """可编程的检索桩：记录调用、按关键词返回预置结果或抛错。"""

    def __init__(self, results: Optional[Sequence[SearchResult]] = None,
                 results_fn=None, fail_for: Sequence[str] = (),
                 empty_for: Sequence[str] = ()) -> None:
        self.calls: List[str] = []
        self._results = list(results or [])
        self._results_fn = results_fn
        self.fail_for: Set[str] = set(fail_for)
        self.empty_for: Set[str] = set(empty_for)

    async def search(self, keyword: str) -> List[SearchResult]:
        self.calls.append(keyword)
        if keyword in self.fail_for:
            raise SearchError("stub failure for {0!r}".format(keyword))
        if keyword in self.empty_for:
            return []
        if self._results_fn is not None:
            return list(self._results_fn(keyword))
        return list(self._results)


class CountingEngine:
    """记录 `run` 调用次数的引擎桩，用于验证 400 分支不触发检索。"""

    def __init__(self) -> None:
        self.run_calls = 0

    async def run(self, topic: str) -> ResearchResponse:
        self.run_calls += 1
        return ResearchResponse(topic=topic, summary="不应被调用")


def make_client(engine: Optional[object] = None,
                service: Optional[object] = None) -> TestClient:
    """用 dependency_overrides 装配测试替身（由 autouse fixture 统一清理）。"""
    if engine is not None:
        app.dependency_overrides[get_engine] = lambda: engine
    if service is not None:
        app.dependency_overrides[get_search_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _result(title: str, url: str) -> SearchResult:
    return SearchResult(title=title, url=url)


# --------------------------------------------------------------------------- #
# 1.2 契约模型
# --------------------------------------------------------------------------- #
def test_models_contract_field_sets():
    response = ResearchResponse(topic="t", summary="s")
    assert set(response.model_dump().keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    assert ResearchRequest().topic == ""
    assert set(SearchResult(title="t", url="u").model_dump().keys()) == {"title", "url"}


# --------------------------------------------------------------------------- #
# 2.1 / 2.2 检索服务抽象与确定性模拟实现
# --------------------------------------------------------------------------- #
def test_search_service_protocol_is_importable():
    assert SearchError is not None
    assert SearchService is not None


def test_mock_search_is_deterministic():
    service = MockSearchService()

    first = asyncio.run(service.search("主流 Agent 框架对比"))
    second = asyncio.run(service.search("主流 Agent 框架对比"))

    assert first == second, "同一 keyword 两次调用结果必须完全相同"
    assert 1 <= len(first) <= 3, "每个关键词应返回 1~3 条结果"
    assert all(item.url and item.title for item in first)

    # 不同 keyword 可能返回相同 URL（去重场景的数据基础）。
    keywords = [
        "LangGraph", "OpenAI Agents SDK", "AutoGen", "CrewAI", "Dify",
        "LlamaIndex", "Semantic Kernel", "Agent 编排", "多智能体", "工具调用",
    ]
    urls_by_keyword: Dict[str, Set[str]] = {
        keyword: {item.url for item in asyncio.run(service.search(keyword))}
        for keyword in keywords
    }
    shared = None
    for i, left in enumerate(keywords):
        for right in keywords[i + 1:]:
            if urls_by_keyword[left] & urls_by_keyword[right]:
                shared = (left, right, urls_by_keyword[left] & urls_by_keyword[right])
                break
        if shared:
            break

    assert shared is not None, "应存在两个 keyword 返回同一 URL"


# --------------------------------------------------------------------------- #
# 3.1 关键词生成可复现
# --------------------------------------------------------------------------- #
def test_generate_keywords_is_reproducible():
    engine = ResearchEngine(StubSearchService())

    first = engine.generate_keywords("主流 Agent 框架对比")
    second = engine.generate_keywords("主流 Agent 框架对比")

    assert first, "有效主题必须至少生成一个关键词"
    assert all(keyword.strip() for keyword in first)
    assert first == second, "同一主题重复生成必须得到完全相同的序列"
    assert engine.generate_keywords("   ") == [], "空主题不应生成关键词"


def test_generate_keywords_follow_up_round_derives_from_previous():
    engine = ResearchEngine(StubSearchService())
    previous = engine.generate_keywords("主题", 0)
    follow_up = engine.generate_keywords("主题", 1, previous)

    assert follow_up, "补检索轮次必须生成关键词"
    assert set(follow_up).isdisjoint(set(previous))
    assert follow_up == engine.generate_keywords("主题", 1, previous)


# --------------------------------------------------------------------------- #
# 3.2 检索委托与结果汇总
# --------------------------------------------------------------------------- #
def test_search_delegates_to_injected_service():
    service = StubSearchService(results=[_result("标题", "https://example.com/a")])
    engine = ResearchEngine(service)

    results = asyncio.run(engine.search("kw"))

    assert service.calls == ["kw"], "引擎必须把检索委托给注入的服务"
    assert [item.url for item in results] == ["https://example.com/a"]


def test_search_degrades_to_empty_on_error():
    engine = ResearchEngine(StubSearchService(fail_for=["kw"]))
    assert asyncio.run(engine.search("kw")) == []


def test_summarize_non_empty_for_results_and_empty_for_no_results():
    engine = ResearchEngine(StubSearchService())

    assert engine.summarize("kw", []) == ""
    text = engine.summarize("kw", [_result("标题", "https://example.com/a")])
    assert isinstance(text, str)
    assert text.strip(), "非空结果必须返回非空字符串"


# --------------------------------------------------------------------------- #
# 3.3 充分性判断（Agent 式判断）
# --------------------------------------------------------------------------- #
def test_is_sufficient_true_when_enough_material():
    engine = ResearchEngine(StubSearchService())
    sections = [Section(keyword="k", content="有内容")]
    sources = [Source(title="a", url="u1"), Source(title="b", url="u2")]
    assert engine.is_sufficient(sections, sources) is True


def test_is_sufficient_false_for_empty_material():
    engine = ResearchEngine(StubSearchService())
    assert engine.is_sufficient([], []) is False
    assert engine.is_sufficient([Section(keyword="k", content="有内容")], []) is False
    assert engine.is_sufficient([], [Source(title="a", url="u1")]) is False


def test_is_sufficient_threshold_is_configurable():
    sections = [Section(keyword="k", content="有内容")]
    sources = [Source(title="a", url="u1"), Source(title="b", url="u2")]

    strict = ResearchEngine(StubSearchService(), sufficiency_threshold=3)
    loose = ResearchEngine(StubSearchService(), sufficiency_threshold=1)

    assert strict.is_sufficient(sections, sources) is False
    assert loose.is_sufficient(sections, sources) is True


# --------------------------------------------------------------------------- #
# 3.4 run() 组装契约与去重
# --------------------------------------------------------------------------- #
def test_run_returns_contract_with_unique_sources():
    service = StubSearchService(results=[
        _result("资料一", "https://example.com/one"),
        _result("资料二", "https://example.com/two"),
    ])
    engine = ResearchEngine(service)

    response = asyncio.run(engine.run("主流 Agent 框架对比"))
    payload = response.model_dump()

    assert set(payload.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    assert payload["topic"] == "主流 Agent 框架对比"
    assert payload["summary"].strip()
    assert payload["process"]["rounds"] in (1, 2)
    urls = [item["url"] for item in payload["sources"]]
    assert len(urls) == len(set(urls)), "sources 中不得出现重复 URL"
    assert payload["process"]["keywords"], "process.keywords 不得为空"


def test_run_uses_structural_round_cap_constant():
    assert MAX_ROUNDS == 2


# --------------------------------------------------------------------------- #
# 3.5 max_rounds 构造期下限校验
# --------------------------------------------------------------------------- #
def test_max_rounds_lower_bound_raises_value_error():
    service = StubSearchService()
    with pytest.raises(ValueError):
        ResearchEngine(service, max_rounds=0)
    with pytest.raises(ValueError):
        ResearchEngine(service, max_rounds=-1)


# --------------------------------------------------------------------------- #
# 4.1 / 5.1 POST /api/research 正常路径
# --------------------------------------------------------------------------- #
def test_normal_report_via_api():
    service = StubSearchService(results=[
        _result("资料一", "https://example.com/one"),
        _result("资料二", "https://example.com/two"),
    ])
    client = make_client(service=service)

    response = client.post("/api/research", json={"topic": "主流 Agent 框架对比"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    assert body["topic"] == "主流 Agent 框架对比"
    assert body["summary"].strip()
    assert body["sections"], "正常路径应产出 sections"
    assert all(set(item) == {"keyword", "content"} for item in body["sections"])
    assert all(set(item) == {"title", "url"} for item in body["sources"])
    assert isinstance(body["process"]["keywords"], list)
    assert isinstance(body["process"]["rounds"], int)


# --------------------------------------------------------------------------- #
# 4.2 / 5.2 空主题返回 400 且不触发检索
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("payload", [
    {"topic": ""},
    {"topic": "   \t\n "},
    {},
    {"topic": None},
])
def test_empty_topic_returns_400(payload):
    service = StubSearchService(results=[_result("资料", "https://example.com/x")])
    client = make_client(service=service)

    response = client.post("/api/research", json=payload)

    assert response.status_code == 400
    assert service.calls == [], "空主题不得触发任何检索"


def test_empty_topic_does_not_call_engine():
    engine = CountingEngine()
    client = make_client(engine=engine)

    response = client.post("/api/research", json={"topic": "   "})

    assert response.status_code == 400
    assert engine.run_calls == 0


# --------------------------------------------------------------------------- #
# 5.3 重复 URL 去重（跨轮 + 同一轮内）
# --------------------------------------------------------------------------- #
def test_url_dedup_across_rounds():
    shared = "https://example.com/shared"

    def results_fn(keyword: str) -> List[SearchResult]:
        return [
            _result("共享资料", shared),
            _result(keyword, "https://example.com/{0}".format(keyword)),
        ]

    service = StubSearchService(results_fn=results_fn)
    # 阈值调高以强制走满两轮，验证跨轮去重。
    engine = ResearchEngine(service, sufficiency_threshold=99)

    response = asyncio.run(engine.run("主题"))

    assert response.process.rounds == 2
    urls = [item.url for item in response.sources]
    assert urls.count(shared) == 1, "跨轮重复 URL 只能出现一次"
    assert urls == [shared] + [
        "https://example.com/{0}".format(keyword)
        for keyword in ["主题", "主题 对比", "主题 深入", "主题 对比 深入"]
    ], "去重后必须保持各 URL 首次出现的顺序"


def test_url_dedup_within_single_round():
    duplicate = "https://example.com/dup"

    def results_fn(keyword: str) -> List[SearchResult]:
        return [_result("A", duplicate), _result("B", duplicate)]

    service = StubSearchService(results_fn=results_fn)
    engine = ResearchEngine(service, sufficiency_threshold=1)

    response = asyncio.run(engine.run("主题"))

    urls = [item.url for item in response.sources]
    assert urls == [duplicate], "同一轮内重复 URL 只能出现一次"


# --------------------------------------------------------------------------- #
# 5.4 研究循环不超过两轮
# --------------------------------------------------------------------------- #
def test_rounds_cap_sufficient_uses_single_round():
    service = StubSearchService(results=[
        _result("资料一", "https://example.com/one"),
        _result("资料二", "https://example.com/two"),
    ])
    engine = ResearchEngine(service)

    assert asyncio.run(engine.run("主题")).process.rounds == 1


def test_rounds_cap_insufficient_uses_two_rounds():
    service = StubSearchService(results=[_result("资料一", "https://example.com/one")])
    engine = ResearchEngine(service)

    assert asyncio.run(engine.run("主题")).process.rounds == 2


def test_rounds_cap_never_sufficient_never_exceeds_two():
    class NeverSufficientEngine(ResearchEngine):
        def is_sufficient(self, sections, sources) -> bool:
            return False

    service = StubSearchService(results=[
        _result("资料一", "https://example.com/one"),
        _result("资料二", "https://example.com/two"),
    ])
    engine = NeverSufficientEngine(service)

    response = asyncio.run(engine.run("主题"))

    assert response.process.rounds == 2, "充分性恒为 False 时也不得超过 2 轮"
    assert len(service.calls) <= 2 * MAX_ROUNDS, "检索调用次数不得超过两轮关键词总数"


# --------------------------------------------------------------------------- #
# 5.5 搜索无结果 / 单次失败时系统仍能稳定响应
# --------------------------------------------------------------------------- #
def test_search_failure_all_empty_still_returns_stable_report():
    service = StubSearchService(results=[])
    client = make_client(service=service)

    response = client.post("/api/research", json={"topic": "主题"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    assert body["sections"] == []
    assert body["sources"] == []
    assert body["summary"].strip(), "资料不足时 summary 必须为非空说明文字"


def test_search_failure_partial_exception_skips_failed_keyword():
    def results_fn(keyword: str) -> List[SearchResult]:
        return [_result("资料", "https://example.com/{0}".format(keyword))]

    service = StubSearchService(results_fn=results_fn)
    engine = ResearchEngine(service, sufficiency_threshold=99)
    failing_keyword = engine.generate_keywords("主题", 0)[0]
    service.fail_for.add(failing_keyword)

    client = make_client(engine=engine)
    response = client.post("/api/research", json={"topic": "主题"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    section_keywords = [item["keyword"] for item in body["sections"]]
    assert failing_keyword not in section_keywords, "失败关键词不得产生 sections 条目"
    assert section_keywords, "其余关键词的汇总结果仍应出现在 sections 中"


# --------------------------------------------------------------------------- #
# 7.4 ResilientSearchService：超时 / 重试 / 降级
# --------------------------------------------------------------------------- #
class FailingSearchService:
    """每次都抛 SearchError 的委托实现。"""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, keyword: str) -> List[SearchResult]:
        self.calls += 1
        raise SearchError("always fails for {0!r}".format(keyword))


class SlowSearchService:
    """总是慢于超时阈值的委托实现。"""

    def __init__(self, delay: float = 0.2,
                 results: Optional[Sequence[SearchResult]] = None) -> None:
        self.calls = 0
        self._delay = delay
        self._results = list(results or [])

    async def search(self, keyword: str) -> List[SearchResult]:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return list(self._results)


def test_resilient_passes_through_successful_results():
    delegate = StubSearchService(results=[_result("资料", "https://example.com/ok")])
    service = ResilientSearchService(delegate, timeout=1.0, retries=1)

    results = asyncio.run(service.search("kw"))

    assert [item.url for item in results] == ["https://example.com/ok"]
    assert delegate.calls == ["kw"], "成功时不应重试"


def test_resilient_retries_match_configuration():
    delegate = FailingSearchService()
    service = ResilientSearchService(delegate, timeout=0.05, retries=2)

    with pytest.raises(SearchError):
        asyncio.run(service.search("kw"))

    assert service.max_attempts == 3
    assert delegate.calls == 3, "总尝试次数应为 retries + 1"


def test_resilient_timeout_degrades_to_empty_result():
    delegate = SlowSearchService(delay=0.2,
                                 results=[_result("资料", "https://example.com/slow")])
    service = ResilientSearchService(delegate, timeout=0.01, retries=1)
    engine = ResearchEngine(service)

    assert asyncio.run(engine.search("kw")) == [], "超时最终应降级为空结果"
    assert delegate.calls == 2, "超时后应按配置重试一次"


def test_resilient_failure_still_returns_200_report():
    delegate = FailingSearchService()
    service = ResilientSearchService(delegate, timeout=0.05, retries=1)
    client = make_client(service=service)

    response = client.post("/api/research", json={"topic": "主题"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
    assert body["sections"] == []
    assert body["sources"] == []
    assert body["summary"].strip(), "降级后仍需给出非空说明"
    assert delegate.calls == 2 * 2 * 2, "两轮 × 两关键词 × 两次尝试"


# --------------------------------------------------------------------------- #
# 7.2 每轮关键词与执行过程可追溯
# --------------------------------------------------------------------------- #
def test_rounds_detail_exposes_each_round_keywords(caplog):
    service = StubSearchService(results=[_result("资料", "https://example.com/one")])
    engine = ResearchEngine(service)

    with caplog.at_level(logging.INFO, logger="app.engine"):
        response = asyncio.run(engine.run("主题"))

    process = response.process
    # 既有契约字段的名称与类型保持不变
    assert isinstance(process.keywords, list)
    assert all(isinstance(item, str) for item in process.keywords)
    assert isinstance(process.rounds, int)
    # process.keywords 为两轮关键词的有序去重并集
    assert process.rounds == 2
    assert process.keywords == ["主题", "主题 对比", "主题 深入", "主题 对比 深入"]
    assert len(process.keywords) == len(set(process.keywords))
    # 可选附加字段暴露每轮关键词
    assert process.rounds_detail is not None
    assert [detail.round for detail in process.rounds_detail] == [1, 2]
    assert process.rounds_detail[0].keywords == ["主题", "主题 对比"]
    assert process.rounds_detail[1].keywords == ["主题 深入", "主题 对比 深入"]
    # 结构化日志中可见每轮关键词与每个关键词的结果数
    assert "round=1" in caplog.text
    assert "round=2" in caplog.text
    assert "主题 深入" in caplog.text
    assert "results=1" in caplog.text


def test_rounds_detail_is_optional_field():
    assert ProcessInfo(keywords=["a"], rounds=1).rounds_detail is None


def test_api_process_keeps_backward_compatible_contract():
    service = StubSearchService(results=[_result("资料", "https://example.com/one")])
    client = make_client(service=service)

    body = client.post("/api/research", json={"topic": "主题"}).json()

    assert set(body.keys()) == {"topic", "summary", "sections", "sources", "process"}
    assert isinstance(body["process"]["keywords"], list)
    assert all(isinstance(item, str) for item in body["process"]["keywords"])
    assert isinstance(body["process"]["rounds"], int)
    assert "rounds_detail" in body["process"], "新增字段应为可选附加字段"


# --------------------------------------------------------------------------- #
# 7.1 检索服务可替换（Protocol + 构造函数注入）
# --------------------------------------------------------------------------- #
def test_injected_alternative_implementation_drives_report():
    """注入一个返回预置结果的替代实现（不继承任何基类）。

    本任务（7.1）只新增测试：`app/engine.py` 未被修改——引擎从
    `ResearchEngine.__init__` 接收的 `SearchService` 协议对象既可以是
    `MockSearchService`，也可以是这里的结构化子类型实现。
    """
    preset = [
        _result("预置资料一", "https://preset.example.com/1"),
        _result("预置资料二", "https://preset.example.com/2"),
    ]

    class PresetSearchService:
        def __init__(self) -> None:
            self.calls: List[str] = []

        async def search(self, keyword: str) -> List[SearchResult]:
            self.calls.append(keyword)
            return list(preset)

    service = PresetSearchService()
    engine = ResearchEngine(service)

    response = asyncio.run(engine.run("主题"))

    assert [item.url for item in response.sources] == [item.url for item in preset], \
        "报告的 sources 必须来自注入的实现"
    assert response.sections, "报告的 sections 必须来自注入的实现"
    assert all("预置资料" in section.content for section in response.sections)
    assert service.calls, "研究流程应实际调用注入的实现"
    assert set(response.model_dump().keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }


def test_search_implementations_conform_to_async_protocol():
    import inspect

    assert inspect.iscoroutinefunction(MockSearchService.search)
    assert inspect.iscoroutinefunction(ResilientSearchService.search)
    assert inspect.iscoroutinefunction(StubSearchService.search)


# --------------------------------------------------------------------------- #
# harden-research-engine 4.1
# research-engine「构造参数校验」：7 个 Scenario 逐一覆盖
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("max_rounds", [3, 5])
def test_constructor_validation_max_rounds_above_cap_raises(max_rounds):
    """Scenario: max_rounds 超过上限 —— 构造期抛 ValueError，且不执行任何检索调用。"""
    service = StubSearchService(results=[_result("资料", "https://example.com/x")])

    with pytest.raises(ValueError) as excinfo:
        ResearchEngine(service, max_rounds=max_rounds)

    message = str(excinfo.value)
    assert str(MAX_ROUNDS) in message, "文案应包含上限值"
    assert str(max_rounds) in message, "文案应包含实际值"
    assert service.calls == [], "构造期拒绝不得产生任何检索调用"


@pytest.mark.parametrize("max_rounds", [0, -1])
def test_constructor_validation_max_rounds_below_lower_bound_raises(max_rounds):
    """Scenario: max_rounds 低于下限 —— 两种情况均抛 ValueError。"""
    with pytest.raises(ValueError):
        ResearchEngine(StubSearchService(), max_rounds=max_rounds)


def test_constructor_validation_max_rounds_non_integer_raises():
    """Scenario: max_rounds 非整数 —— 构造期抛 ValueError，而非推迟到 run() 抛 TypeError。"""
    service = StubSearchService()

    with pytest.raises(ValueError):
        ResearchEngine(service, max_rounds=1.5)

    assert service.calls == [], "构造期拒绝不得产生任何检索调用"


def test_constructor_validation_retries_negative_raises():
    """Scenario: retries 为负 —— 构造期抛 ValueError。"""
    with pytest.raises(ValueError):
        ResilientSearchService(StubSearchService(), retries=-1)


def test_constructor_validation_retries_non_integer_raises():
    """Scenario: retries 非整数 —— 构造期抛 ValueError；retries=0 合法且 max_attempts == 1。"""
    with pytest.raises(ValueError):
        ResilientSearchService(StubSearchService(), retries=1.5)

    assert ResilientSearchService(StubSearchService(), retries=0).max_attempts == 1


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_constructor_validation_timeout_non_finite_raises(timeout):
    """Scenario: timeout 非有限（nan / inf / -inf）—— 两种情况均抛 ValueError。"""
    with pytest.raises(ValueError):
        ResilientSearchService(StubSearchService(), timeout=timeout)


@pytest.mark.parametrize("timeout", [0, -1])
def test_constructor_validation_timeout_non_positive_raises(timeout):
    """Scenario: timeout 非正 —— 两种情况均抛 ValueError。"""
    with pytest.raises(ValueError):
        ResilientSearchService(StubSearchService(), timeout=timeout)


# --------------------------------------------------------------------------- #
# harden-research-engine 4.2
# research-engine「最多两轮检索」新增的两个 Scenario
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("max_rounds", [3, 5])
def test_rounds_cap_raising_max_rounds_is_rejected(max_rounds):
    """Scenario: 构造参数调高被拒绝 —— ValueError 且检索调用为 0。"""
    service = StubSearchService(results=[_result("资料", "https://example.com/x")])

    with pytest.raises(ValueError):
        ResearchEngine(service, max_rounds=max_rounds)

    assert service.calls == []


def test_rounds_cap_lowered_to_one_executes_single_round():
    """Scenario: 构造参数调低到 1 时只执行一轮（充分性恒为不充分）。"""

    class NeverSufficientEngine(ResearchEngine):
        def is_sufficient(self, sections, sources) -> bool:
            return False

    service = StubSearchService(results=[
        _result("资料一", "https://example.com/one"),
        _result("资料二", "https://example.com/two"),
    ])
    engine = NeverSufficientEngine(service, max_rounds=1)

    response = asyncio.run(engine.run("主题"))

    assert response.process.rounds == 1
    assert response.process.keywords == ["主题", "主题 对比"], "只应包含第一轮关键词"
    assert service.calls == ["主题", "主题 对比"], "检索次数等于第一轮关键词数"
    assert not any("深入" in keyword for keyword in service.calls), (
        "不存在第二轮派生关键词的检索"
    )


# --------------------------------------------------------------------------- #
# harden-research-engine 4.3
# research-api「报告结构符合五段式契约」新增的 Scenario
# --------------------------------------------------------------------------- #
def test_topic_normalized_strips_leading_trailing_whitespace():
    """Scenario: 主题首尾空白被规范化后回显 —— 200 且 topic == "主题"。"""
    service = StubSearchService(results=[_result("资料", "https://example.com/x")])
    client = make_client(service=service)

    response = client.post("/api/research", json={"topic": "  主题  "})

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "主题", "topic 必须回显去除首尾空白后的主题"
    assert set(body.keys()) == {
        "topic", "summary", "sections", "sources", "process",
    }
