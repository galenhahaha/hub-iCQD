## Why

第二轮独立验收（变异测试、20 个 Scenario 追溯矩阵、对抗性探测）结论为"有条件通过"：对外 HTTP 行为与既有 43 个测试均正常，但暴露出三类"规格与实现不一致"的缺口——两轮上限可被构造参数突破（`ResearchEngine(svc, max_rounds=5)` 真的跑 5 轮、10 次检索，违反主规格「最多两轮检索」的 SHALL）、构造期参数校验不完整（非整数 `max_rounds`、`NaN` 超时被放行）、以及两处规格措辞与实现不符。用户已就每项裁决处置方式（构造期硬校验 + 改规格措辞 + 修正文档漂移），本次据此收口。

## What Changes

- **BREAKING（仅影响进程内构造调用方，不影响 HTTP 契约）**：`ResearchEngine.__init__` 在 `max_rounds > MAX_ROUNDS`（`MAX_ROUNDS = 2`）时抛 `ValueError`。`MAX_ROUNDS` 成为**不可被配置突破的绝对上限**，构造参数只可**调低**（便于测试单轮路径），不可**调高**。
- `ResearchEngine.__init__` 增加类型校验：`max_rounds` 必须是整数类型（非整数如 `1.5` 在构造期抛 `ValueError`，不再推迟到 `run()` 抛 `TypeError`）。
- `ResilientSearchService.__init__` 增加参数校验：`timeout` 必须是**有限正数**（拒绝 `NaN` 与 `Inf`；当前 `NaN` 能通过 `timeout <= 0` 检查，表现为立即超时，等价于 `timeout=0`）；`retries` 必须是非负整数。
- 修改 `research-engine` 主规格「最多两轮检索」：明确该上限是**不可被配置突破的不变量**，补充"调高被拒绝""调低到 1 生效"两个 Scenario。
- 新增 `research-engine` 需求「构造参数校验」，Scenario 覆盖 `max_rounds > 2`、`max_rounds < 1`、`max_rounds` 非整数、`retries` 为负、`retries` 非整数、`timeout` 非有限、`timeout` 非正。
- 修改 `research-api` 主规格「研究接口生成研究报告」措辞：`topic` 回显**规范化（去除首尾空白）后**的主题（实现早已 `.strip()`，规格原文写的是"回显请求中的主题"）。
- 修改 `research-engine` 主规格「研究流程按四步职责编排」措辞：明确职责顺序是**逐轮**组织的（每轮：生成关键词 → 对每个关键词 `search` → `summarize` → 本轮末 `is_sufficient`），排除"先全部检索、再全部汇总"的分阶段读法。
- 修正文档漂移（D-4 / D-5）：`docs/architecture.md` 的日志描述、`README.md` 与 `docs/architecture.md` 关于 `is_sufficient` 的表述改为与实现一致。

### 不在范围（已发现但本次不处理）

- D-7：同步（非 async）检索实现被 `ResearchEngine.search()` 的兜底 `except` 静默降级为空结果。
- D-8：`MockSearchService.search(123)` 抛 `AttributeError`（非字符串入参未校验）。
- F-2：零宽空格 `"​"` 被视为有效主题（`str.strip()` 不视其为空白）。
- `sufficiency_threshold` 的类型与下限校验（本次未要求，且不影响既有对外行为）。

## Capabilities

### New Capabilities

无。本次不引入新能力，只收紧既有能力的需求与措辞。

### Modified Capabilities

- `research-engine`: 「最多两轮检索」改为不可被配置突破的不变量；新增「构造参数校验」需求（`max_rounds` / `retries` / `timeout`）；「研究流程按四步职责编排」措辞澄清为逐轮顺序。
- `research-api`: 「研究接口生成研究报告」中 `topic` 回显语义改为"回显规范化后的主题"，并补充对应 Scenario。

## Impact

- 修改文件：`app/engine.py`（`ResearchEngine.__init__` 构造期校验）、`app/services.py`（`ResilientSearchService.__init__` 构造期校验）、`tests/`（新增构造期校验用例）、`docs/architecture.md` 与 `README.md`（D-4 / D-5 表述修正）。
- 不变：HTTP 契约（200/400/422 状态码、五段式响应结构）、URL 去重、失败与空结果降级、`process.rounds` 为实际执行轮数（1 或 2）的语义。
- 兼容性：既有 43 个测试必须全绿；测试中现有取值（`max_rounds=0/-1`、`sufficiency_threshold=99`、`timeout=0.01/0.05/1.0`、`retries=1/2`）均在合法范围内。
- 不涉及：前端、数据库、用户系统、部署、MCP、多 Agent SDK、真实网络检索与真实 LLM 调用；不在代码、日志或提交记录中存放任何密钥。
