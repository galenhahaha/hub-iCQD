## Context

本仓库当前为空项目（无 `app/`、`tests/`、`requirements.txt`，`openspec/specs/` 仅有 `.gitkeep`），因此本设计是一次从零搭建，不涉及存量代码迁移。动机与范围见 `proposal.md`，行为契约见 `specs/research-api/spec.md` 与 `specs/research-engine/spec.md`；本文件只回答"怎么实现"。

约束（来自 `README.md`、`CLAUDE.md`）：

- 技术栈固定 Python + FastAPI + Pydantic + pytest；第一版搜索与"模型"均为**本地确定性模拟**，不联网、不调真实 LLM。
- 必须显式暴露四项职责：`generate_keywords(topic)`、`search(keyword)`、`summarize(keyword, results)`、`is_sufficient(...)`。
- 硬性行为：最多两轮；URL 去重；空/全空白 `topic` → 400；搜索无结果或单次失败不崩溃。
- 不得在代码、日志、提交记录中出现密钥。

## Goals / Non-Goals

**Goals:**

- 让"研究流程"这条链路有一个唯一、可读、可单测的编排入口，停止条件在结构上不可违反。
- 把"判断资料是否充分"抽成流程中唯一的一个决策点，使其未来可替换为 LLM 驱动实现而不改动编排骨架。
- 把搜索这一外部依赖隔离在抽象接口之后，测试可注入桩、生产可换真实服务。
- 让 README 第 5 节的 5 个场景都能用 pytest 确定性复现。

**Non-Goals:**

- 不引入真实网络搜索、真实 LLM、向量库、缓存或消息队列。
- 不做关键词检索的并发优化（第一版串行即可，接口已异步以保留空间）。
- 不做 URL 归一化/可达性探测（去重只按字符串精确相等）。
- 不做前端、数据库、用户系统、部署、MCP、多 Agent SDK。
- 不为"展示设计模式"引入额外抽象层（如仓储层、事件总线）。

## 模块划分

```text
app/
├── __init__.py
├── models.py       # Pydantic 契约模型 + 领域 DTO（SearchResult）
├── services.py     # SearchService 抽象 + MockSearchService + SearchError (+ 可选 ResilientSearchService)
├── engine.py       # ResearchEngine：Workflow 控制 + Agent 式判断 + 汇总去重
└── main.py         # FastAPI 应用、POST /api/research、400 校验、依赖注入装配
tests/
└── test_research.py
```

| 模块 | 职责 | 不做的事 |
| --- | --- | --- |
| `models.py` | 请求/响应契约、`SearchResult` DTO | 不含业务流程、不发 IO |
| `services.py` | 检索能力的抽象与本地实现、检索异常类型、可选超时/重试包装 | 不知道"轮次""充分性"，不拼装报告 |
| `engine.py` | 关键词生成、逐关键词检索与汇总、充分性判断、轮次控制、URL 去重、报告组装 | 不感知 HTTP、不感知 FastAPI |
| `main.py` | 路由、请求校验与 400、依赖装配 | 不写研究逻辑 |

## Decisions

### D1. Workflow 控制落在 `ResearchEngine.run()`

`ResearchEngine.run(topic: str) -> ResearchResponse` 是唯一的编排者，也是"Workflow 控制"的落点。它按固定顺序执行：

```python
def run(self, topic: str) -> ResearchResponse:
    rounds_detail: list[RoundRecord] = []
    sections: list[Section] = []
    seen_urls: dict[str, Source] = {}          # 保序去重

    for round_index in range(self._max_rounds):      # 见 D3
        keywords = self.generate_keywords(topic, round_index, rounds_detail)
        if not keywords:
            break
        round_sections, round_sources = [], []
        for keyword in keywords:
            results = self.search(keyword)           # 见 D5，容错在此
            summary_text = self.summarize(keyword, results)
            if summary_text:
                round_sections.append(Section(keyword=keyword, content=summary_text))
            round_sources.extend(results)
        sections.extend(round_sections)
        for item in round_sources:                   # URL 去重（D6）
            seen_urls.setdefault(str(item.url), Source(title=item.title, url=item.url))
        rounds_detail.append(RoundRecord(round=round_index + 1, keywords=list(keywords)))

        if self.is_sufficient(sections, list(seen_urls.values())):   # 见 D2
            break

    return ResearchResponse(...)  # topic/summary/sections/sources/process
```

所有"顺序、状态、何时停"都集中在这一个方法里，因此单测只需替换注入的检索服务与（必要时）`is_sufficient` 即可覆盖全部分支。

**替代方案**：把每轮做成独立函数/状态机对象。否决——两轮的规模下状态机是过度设计，且会让"轮次上限"从结构保证退化为状态迁移保证，更难一眼验证。

### D2. Agent 式判断落在 `ResearchEngine.is_sufficient(...)`

`is_sufficient(sections, sources) -> bool` 是流程中**唯一**的决策点：引擎在拿到本轮资料后，自主判断"现有资料够不够，要不要再补一轮"。这正是 Agent 式判断（自我评估 → 决定是否继续行动）的落点，与 D1 的机械 Workflow 控制明确分离。

- 签名只接收已收集的汇总结果，不读引擎内部状态 → 可脱离流程单测。
- 第一版判据确定性可复现：`存在至少一个 content 非空的 section` 且 `去重后来源数 >= sufficiency_threshold`（默认 2，构造参数可调）。
- 未来替换为 LLM 判断时，保持同一签名、同一返回类型，`run()` 无需改动。

**替代方案**：把判断内联进 `run()` 的 `if` 里。否决——那样"判断"与"控制"耦合，无法独立测试，也无法替换为真实模型判断。

### D3. 两轮上限由结构保证，而非计数器

```python
MAX_ROUNDS = 2   # 模块级常量，作为构造参数默认值
for round_index in range(self._max_rounds):   # 迭代次数在进入循环前就固定为 2
    ...
    if self.is_sufficient(...):
        break
```

- 使用 `for ... in range(2)` 而非 `while`：循环体的执行次数由 `range` 对象在构造时确定，**物理上不可能出现第三轮**，即使 `is_sufficient` 永远返回 `False`、即使轮次计划被错误修改。
- `break` 只用于"提前结束"，不用于"控制上限"，因此不会出现"计数器写错导致多跑一轮"的风险。
- `self._max_rounds` 有下限校验（构造时 `if max_rounds < 1: raise ValueError`），避免被误设为 0 或负数导致行为异常。
- `process.rounds` 取自 `len(rounds_detail)`，是**实际执行轮数**，与上限解耦。

**替代方案**：`while round_no < 2` + 手动自增。否决——自增语句可被漏写或写错，上限不再是结构性保证。另一方案：预先构建长度为 2 的轮次计划列表再遍历。否决——第二轮关键词依赖第一轮结果（补检索要针对资料缺口），预先构建会牺牲适应性。

### D4. 搜索服务通过 `Protocol` 抽象 + 构造函数依赖注入隔离

```python
# services.py
class SearchError(Exception): ...

class SearchService(Protocol):
    async def search(self, keyword: str) -> list[SearchResult]: ...

class MockSearchService:
    """确定性本地实现：同一 keyword 永远返回同一组结果。"""
    async def search(self, keyword: str) -> list[SearchResult]: ...

# engine.py
class ResearchEngine:
    def __init__(self, search_service: SearchService, *, max_rounds: int = MAX_ROUNDS,
                 sufficiency_threshold: int = 2) -> None:
        self._search_service = search_service
        ...
    async def search(self, keyword: str) -> list[SearchResult]:
        try:
            return await self._search_service.search(keyword)
        except SearchError as exc:
            logger.warning("search failed for %r: %s", keyword, exc)
            return []
        except Exception as exc:                      # 兜底：任何异常都降级为空结果
            logger.exception("unexpected search error for %r", keyword)
            return []
```

- 依赖从构造函数进入（依赖注入），而非在引擎内部 `MockSearchService()` 硬编码 → 测试注入桩、生产注入真实服务都不改引擎代码。
- 选 `typing.Protocol`（结构化子类型）而非 `abc.ABC`：测试桩无需继承即可满足类型契约，耦合更低；同时保留静态类型检查能力。代价见 Risks。
- `ResearchEngine.search()` 是引擎对外暴露的职责方法（满足 README §4.2），内部只做委托 + 容错降级，把"失败不崩溃"这条硬约束收敛到**一个**地方。
- FastAPI 侧在 `main.py` 用 `Depends(get_engine)` 装配；测试用 `app.dependency_overrides[get_engine] = lambda: ResearchEngine(FakeSearchService(...))` 替换。
- 加分的超时/重试/降级做成**装饰器式包装** `ResilientSearchService(delegate, timeout=..., retries=...)`（`asyncio.wait_for` + 有限重试，最终失败抛 `SearchError` 由引擎降级）。包装器实现同一 `SearchService` 协议，因此对引擎完全透明。

### D5. 400 校验放在路由层显式抛出，不放 Pydantic validator

`ResearchRequest.topic` 声明为 `topic: str = ""`（字段缺失 → 空串），路由函数中显式判断：

```python
@app.post("/api/research", response_model=ResearchResponse)
async def research(payload: ResearchRequest, engine: ResearchEngine = Depends(get_engine)):
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic 不能为空")
    return await engine.run(topic)
```

**为什么**：若用 Pydantic `field_validator` 抛 `ValueError`，FastAPI 会返回 422 而非需求要求的 400。放在路由层可精确控制状态码，并保证"校验失败时一次检索都不发生"（引擎尚未被调用）。非字符串类型仍由 Pydantic 返回 422（见 proposal 假设 3）。

### D6. URL 去重按字符串精确相等、保留首次出现顺序

用 `dict[str, Source]` + `setdefault` 实现：Python 3.7+ 的 dict 保序，`setdefault` 保证"首次出现者胜出"。去重范围覆盖**所有轮次**（跨轮去重），与 `specs/research-engine/spec.md` 的去重场景一致。不做 scheme/host 归一化——README 未要求，避免过度设计。

### D7. 每轮关键词的记录方式

引擎内部维护 `rounds_detail: list[RoundRecord]`（`round` + `keywords`），并逐轮写日志（轮次、关键词、每个关键词的结果数/失败原因）。`process.keywords` 为所有轮次关键词的**有序去重并集**，`process.rounds = len(rounds_detail)`。加分项要求的"每轮执行过程"通过日志 + `process` 的**可选附加字段** `rounds_detail` 暴露，五段式契约字段名与类型不变（见 `specs/research-api/spec.md` 的向后兼容需求）。

### D8. 异步化作为增量：目标态全链路 `async def`

**目标态**是路由、引擎、检索服务统一使用 `async def`，使"替换为真实网络服务"不需要改签名。但异步在本项目中属加分项，且第一版 `MockSearchService` 无 IO、异步不带来性能收益，因此按最小可用优先拆分：**最小可运行版本先用同步 `def` 签名**（FastAPI 同步路由会在线程池执行，行为正确），随后由加分项任务统一升级为 `async def`——签名升级是机械改动，引擎编排逻辑不变。这样既不阻塞最小版本交付，也不牺牲目标态的替换点。

### D9. 确定性 mock 的取值策略

`MockSearchService` 由 `keyword` 的稳定哈希派生固定的 1~3 条结果（标题/URL 形如 `https://example.com/<slug>`），同一 keyword 永远返回同一组数据；不同关键词可能返回**相同 URL**，用于构造跨关键词/跨轮次的去重场景。补检索（第二轮）的关键词由 `generate_keywords(topic, round_index, previous)` 在第一轮关键词基础上派生（如追加限定词），保证第二轮结果与第一轮不同但仍确定。

## Risks / Trade-offs

- [确定性 mock 可能让"资料不足 → 第二轮"路径在默认参数下不被触发] → 充分性阈值与 `max_rounds` 均为构造参数；测试通过注入返回少量结果的桩服务或调高阈值来稳定覆盖两轮与"恒不充分"路径。
- [`Protocol` 是结构化类型，运行时不做实例校验，传错实现只在调用时暴露] → 依赖静态类型标注 + 测试中注入桩即验证契约；`MockSearchService` 与 `ResilientSearchService` 各写一次协议一致性测试。
- [串行逐关键词检索在真实服务下延迟叠加] → 第一版接受；`search` 已为 async，后续可用 `asyncio.gather` 并行化而不改签名。
- [超时/重试包装可能放大总延迟] → 参数取小值（如 timeout 2s、retries 1）且只包在外部服务边界，引擎侧仍有"降级为空结果"兜底。
- [顶层 `except Exception` 兜底可能掩盖真实 bug] → 兜底处使用 `logger.exception` 记录堆栈，并只在 `search()` 这一层收口，不吞掉编排层异常。
- [所有搜索都失败时返回 200 空报告，调用方可能误读为"没有资料"] → `summary` 显式说明资料不足，并在 `sources` 为空时保持结构完整，让调用方可区分"空结果"与"服务异常"。

## Migration Plan

全新项目，无数据或接口迁移。落地顺序即 `tasks.md` 的顺序：先最小可运行版本（模型 → 服务 → 引擎 → 路由 → 正常路径测试），再补异常处理与边界测试，最后做加分项。回滚策略：删除本次新增文件即可，不影响任何存量资产。

## Open Questions

以下问题不影响规格、方案或任务拆解，可留待后续迭代决定：

- 是否将关键词检索并行化（`asyncio.gather`）以及并发上限取值。
- 真实搜索服务/LLM 的接入形式（HTTP 客户端、SDK、MCP）——本次明确不做。
- `sources` 是否需要携带摘要片段或发布时间等字段（当前契约只要求 `title` 与 `url`）。
