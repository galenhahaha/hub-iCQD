## 1. 引擎构造期校验（D-1 / D-2）

- [x] 1.1 在 `app/engine.py` 的 `ResearchEngine.__init__` 增加 `max_rounds` 上限校验：`max_rounds > MAX_ROUNDS` 时抛 `ValueError`（文案含实际值与上限），验证方式：新增单测断言 `ResearchEngine(svc, max_rounds=3)` 与 `max_rounds=5` 均抛 `ValueError`，且注入的计数桩记录检索调用次数为 0。
- [x] 1.2 在 `ResearchEngine.__init__` 增加 `max_rounds` 类型校验：非整数（如 `1.5`）抛 `ValueError` 而非推迟到 `run()` 抛 `TypeError`；保留既有 `max_rounds < 1` 抛 `ValueError` 的行为，验证方式：新增单测断言 `max_rounds=1.5`、`0`、`-1` 三种取值均在构造期抛 `ValueError`，且异常类型统一为 `ValueError`。
- [x] 1.3 保持 `run()` 的 `for round_index in range(self._max_rounds)` 结构不变，并确认"调低生效"：`max_rounds=1` 且充分性恒为不充分时只执行一轮，验证方式：新增单测断言 `process.rounds == 1`、`process.keywords` 恰为第一轮关键词、检索调用次数等于第一轮关键词数（不存在第二轮派生关键词）。
- [x] 1.4 更新 `app/engine.py` 中 `MAX_ROUNDS` 的注释与 `ResearchEngine.__init__` 的 docstring，写明"`MAX_ROUNDS` 为不可突破的绝对上限，`max_rounds` 只可调低、调高即构造期拒绝"，验证方式：代码审阅确认注释与 docstring 表述与实现一致，且 `MAX_ROUNDS == 2` 未变。

## 2. 检索包装器构造期校验（D-6）

- [x] 2.1 在 `app/services.py` 的 `ResilientSearchService.__init__` 把 `timeout` 校验收紧为"有限正数"（拒绝 `NaN`、`±Inf`、`0`、负数），验证方式：新增单测断言 `timeout=float("nan")`、`float("inf")`、`float("-inf")`、`0`、`-1` 五种取值均抛 `ValueError`。
- [x] 2.2 在 `ResilientSearchService.__init__` 增加 `retries` 类型校验：非负整数（非整数如 `1.5` 抛 `ValueError`；`retries=0` 合法），验证方式：新增单测断言 `retries=-1` 与 `retries=1.5` 抛 `ValueError`，且 `retries=0` 构造成功、`max_attempts == 1`。
- [x] 2.3 确认既有超时/重试行为不变，验证方式：`pytest -q tests/test_research.py -k resilient` 全部通过（覆盖 `timeout=0.01/0.05/1.0`、`retries=1/2` 的既有用例）。

## 3. 规格措辞与文档修正（D-3 / F-1 / D-4 / D-5）

- [x] 3.1 修正 `docs/architecture.md` 第 5 节日志描述（D-4）：改为"充分时输出 `round=N sufficient=true`，不充分时不输出该行；另有 `round=N done sections=.. unique_sources=..` 行"，验证方式：逐条比对 `app/engine.py` 中 `logger.info` 的实际调用（`round=%d keywords=...`、`round=%d keyword=%r results=%d`、`round=%d done sections=%d unique_sources=%d`、`round=%d sufficient=true`），文档描述与代码一致。
- [x] 3.2 修正 `is_sufficient` 表述（D-5）：`docs/architecture.md` 第 2 节与 `README.md` 第 10 节中"不读取引擎内部状态"改为"不读取流程累积状态；阈值来自构造配置 `sufficiency_threshold`"，验证方式：两份文档中不再出现"不读取引擎内部状态"的表述，且新表述与 `app/engine.py` 中 `is_sufficient` 实际读取 `self._sufficiency_threshold` 的行为一致。
- [x] 3.3 确认措辞修正不改变任何代码行为，验证方式：`git diff --stat`（或文件比对）显示 `app/`、`tests/` 中与 `topic` 规范化、职责顺序相关的代码零改动；`pytest -q` 仍全绿。

## 4. 新增测试（覆盖 delta 的全部新增/修改 Scenario）

- [x] 4.1 为 `research-engine` 新需求「构造参数校验」补齐测试，逐条覆盖 7 个 Scenario：`max_rounds > 2`、`max_rounds < 1`、`max_rounds` 非整数、`retries` 为负、`retries` 非整数、`timeout` 非有限（`nan` / `inf`）、`timeout` 非正，验证方式：`pytest -q tests/test_research.py -k constructor_validation` 全部通过（每个 Scenario 至少一个断言）。
- [x] 4.2 为 `research-engine`「最多两轮检索」新增的两个 Scenario 补测试：构造参数调高被拒绝（`ValueError` 且检索调用为 0）、构造参数调低到 1 时只执行一轮，验证方式：`pytest -q tests/test_research.py -k rounds_cap` 通过（含新增用例与既有三例）。
- [x] 4.3 为 `research-api`「报告结构符合五段式契约」新增的 Scenario 补测试：`{"topic": "  主题  "}` 返回 200 且 `topic == "主题"`，验证方式：`pytest -q tests/test_research.py -k topic_normalized` 通过。
- [x] 4.4 核对「职责顺序按轮组织而非分阶段」与「流程按固定顺序执行职责」两个 Scenario 已被既有追溯测试覆盖（`tests/test_spec_traceability.py::test_responsibilities_are_called_in_required_order` 已断言"每轮以 `is_sufficient` 收尾、第二轮检索不早于第一轮判断"），必要时仅补充断言、不改既有断言，验证方式：`pytest -q tests/test_spec_traceability.py` 全部通过，且该用例断言与 delta 措辞逐句对应。

## 5. 收尾验证

- [x] 5.1 运行全量测试并记录真实输出，验证方式：`.venv/bin/pytest -q` 退出码为 0，既有 43 个测试全绿且新增用例全部通过（在收尾报告中贴出完整输出）。
- [x] 5.2 校验变更规格，验证方式：`openspec validate harden-research-engine --strict` 输出 `Change 'harden-research-engine' is valid`。
- [x] 5.3 对外 HTTP 行为回归，验证方式：以默认装配（无 `dependency_overrides`）调用 `POST /api/research`，断言正常主题 200 且响应含 `topic`/`summary`/`sections`/`sources`/`process`、空主题与全空白主题 400、全部检索无结果仍 200 且 `summary` 说明资料不足。
- [x] 5.4 逐条核对 delta 中每个 Scenario 都有对应 pytest 用例（追溯矩阵），验证方式：在收尾报告中给出 Scenario → 测试函数名的一一映射，且不存在无测试的 Scenario。
