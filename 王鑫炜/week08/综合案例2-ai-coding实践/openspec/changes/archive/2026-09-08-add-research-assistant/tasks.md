## 1. 项目骨架与契约模型（最小可运行）

- [x] 1.1 创建 `app/__init__.py` 与 `requirements.txt`（fastapi、uvicorn、pydantic、pytest、httpx），验证方式：运行 `pip install -r requirements.txt` 成功，且 `python -c "import fastapi, pydantic, pytest, httpx"` 无报错。
- [x] 1.2 在 `app/models.py` 定义 `ResearchRequest`（`topic: str = ""`）、`Section`（`keyword`/`content`）、`Source`（`title`/`url`）、`ProcessInfo`（`keywords`/`rounds`）、`ResearchResponse`（`topic`/`summary`/`sections`/`sources`/`process`）与 `SearchResult`（`title`/`url`），验证方式：`python -c "from app.models import ResearchResponse, SearchResult"` 可导入，且构造一个 `ResearchResponse` 实例后断言其字段集合恰为上述五个键。

## 2. 本地模拟搜索服务

- [x] 2.1 在 `app/services.py` 定义 `SearchError` 异常与 `SearchService` 基类（`search(keyword) -> list[SearchResult]`），验证方式：`python -c "from app.services import SearchService, SearchError"` 可导入。
- [x] 2.2 实现确定性 `MockSearchService`：由 keyword 稳定派生 1~3 条 `SearchResult`，同一 keyword 重复调用结果完全相同，且不同 keyword 可能返回相同 URL，验证方式：`pytest tests/test_research.py -k mock_search_is_deterministic` 通过（断言两次调用结果相等，并断言存在两个 keyword 返回同一 URL）。

## 3. ResearchEngine 最小流程

- [x] 3.1 实现 `ResearchEngine.generate_keywords(topic, round_index=0, previous=None)`，验证方式：单元测试断言有效主题返回至少一个非空关键词，且同一主题重复调用得到相同序列。
- [x] 3.2 实现 `ResearchEngine.search(keyword)` 与 `ResearchEngine.summarize(keyword, results)`，验证方式：单元测试断言 `search` 调用注入服务的 `search`（用计数桩证明委托发生），`summarize` 对非空结果返回非空字符串、对空列表返回空字符串。
- [x] 3.3 实现 `ResearchEngine.is_sufficient(sections, sources)`（默认阈值 2，构造参数 `sufficiency_threshold` 可调，不读取引擎内部状态），验证方式：单元测试断言资料充分时返回 `True`、空资料时返回 `False`。
- [x] 3.4 实现 `ResearchEngine.run(topic)`：用 `for round_index in range(self._max_rounds)` 结构、充分则 `break`、逐轮调用四步职责、跨轮按 URL 保序去重、组装 `ResearchResponse`，验证方式：单元测试断言返回对象含五个契约字段，`process.rounds` 为 1 或 2，`sources` 中无重复 URL。
- [x] 3.5 为 `_max_rounds` 增加构造期下限校验，验证方式：单元测试断言 `ResearchEngine(service, max_rounds=0)` 与 `max_rounds=-1` 均抛 `ValueError`。

## 4. FastAPI 接口与输入校验

- [x] 4.1 在 `app/main.py` 实现 `POST /api/research` 与 `get_engine()` 依赖提供者，验证方式：`TestClient(app).post("/api/research", json={"topic": "主流 Agent 框架对比"})` 返回 200，且响应 JSON 含 `topic`/`summary`/`sections`/`sources`/`process`。
- [x] 4.2 实现空主题校验：`topic` 为空字符串、全空白字符串或字段缺失时返回 HTTP 400，且不调用引擎，验证方式：三个用例均断言状态码 400；再注入记录调用次数的桩引擎后断言调用次数为 0。

## 5. README 第 5 节必测的 5 个场景

- [x] 5.1 编写"正常输入能够生成报告"测试，验证方式：`pytest tests/test_research.py -k normal_report` 通过（对应 `research-api` 的正常主题与五段式结构场景）。
- [x] 5.2 编写"空主题返回 HTTP 400"测试，覆盖空字符串、全空白、字段缺失三种输入，验证方式：`pytest tests/test_research.py -k empty_topic` 通过。
- [x] 5.3 编写"重复 URL 被正确去重"测试，覆盖跨轮重复与同一轮内重复两种情形，验证方式：`pytest tests/test_research.py -k url_dedup` 通过（断言该 URL 只出现一次且顺序为首次出现顺序）。
- [x] 5.4 编写"研究循环不会超过两轮"测试，覆盖充分→1 轮、不充分→2 轮、充分性判断恒为 `False`→不超过 2 轮三种情形，验证方式：`pytest tests/test_research.py -k rounds_cap` 通过。
- [x] 5.5 编写"搜索无结果时系统仍能稳定响应"测试，覆盖全部检索返回空结果与部分关键词检索抛异常两种情形，验证方式：`pytest tests/test_research.py -k search_failure` 通过（断言状态码 200、结构完整、失败关键词无 `sections` 条目）。

## 6. README 与可运行性

- [x] 6.1 在 `README.md` 追加安装、启动、测试命令，验证方式：按文档执行 `uvicorn app.main:app --reload` 可启动，并用 `curl -X POST http://127.0.0.1:8000/api/research -H 'Content-Type: application/json' -d '{"topic":"主流 Agent 框架对比"}'` 得到 200 报告。
- [x] 6.2 在 README 说明 Workflow 控制与 Agent 式判断的代码位置，验证方式：文档中可直接定位到 `ResearchEngine.run()`（Workflow 控制）与 `ResearchEngine.is_sufficient()`（Agent 式判断）。

## 7. 加分项

- [x] 7.1 用 `typing.Protocol` 形式化 `SearchService` 抽象并保留构造函数注入，验证方式：新增测试注入一个返回预置结果的替代实现，断言报告的 `sections`/`sources` 来自该实现，且 `engine.py` 未作修改。
- [x] 7.2 记录每轮关键词与执行过程：引擎维护 `rounds_detail`、逐轮写结构化日志，并在 `process` 中新增可选字段暴露每轮关键词，验证方式：测试断言两轮后 `process.keywords` 为有序去重并集、`process.rounds == 2`、可选字段含两轮关键词，且日志中可见每轮关键词（`caplog` 断言）。
- [x] 7.3 全链路异步化：路由、引擎、检索服务签名改为 `async def`，验证方式：`pytest -q` 全部通过，且 `app/main.py` 中路由函数为 `async def`、`app/engine.py` 中 `run`/`search` 为 `async def`。
- [x] 7.4 实现 `ResilientSearchService(delegate, timeout, retries)` 超时/重试/降级包装（超时用 `asyncio.wait_for`，最终失败抛 `SearchError` 由引擎降级），验证方式：注入超时桩与抛错桩，断言重试次数符合配置、最终降级为空结果、接口仍返回 200 报告。
- [x] 7.5 编写简短架构说明与改进方向（README 章节或 `docs/` 文件），验证方式：文档包含 Workflow 控制落点、Agent 式判断落点、依赖注入边界、两轮停止条件的结构性说明。

## 8. 收尾验证

- [x] 8.1 运行 `pytest -q` 全量测试并记录真实输出，验证方式：命令退出码为 0 且无失败用例。
- [x] 8.2 运行 `openspec validate add-research-assistant --strict` 验证变更规格仍有效，验证方式：输出 `Change 'add-research-assistant' is valid`。
