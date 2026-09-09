## Context

动机与范围见 `proposal.md`，需求以 `specs/` 下的 delta 为准。本文件只说明"怎么做"。

当前实现的相关事实（`app/engine.py`、`app/services.py`）：

- `ResearchEngine.__init__` 只校验 `max_rounds < 1`，对 `max_rounds > MAX_ROUNDS` 与非整数一律放行；轮数上限由 `for round_index in range(self._max_rounds)` 在结构上保证，但 `_max_rounds` 本身没有上界约束，因此"最多两轮"可被构造参数绕过（`max_rounds=5` 会真的跑 5 轮、10 次检索，且第 3 轮起关键词重复）。
- `ResilientSearchService.__init__` 只校验 `timeout <= 0` 与 `retries < 0`；`float("nan") <= 0` 为 `False`，故 `NaN` 通过校验，并在 `asyncio.wait_for(..., timeout=nan)` 下表现为立即超时。
- 既有 43 个测试全绿；测试中使用的构造取值（`max_rounds=0/-1`、`sufficiency_threshold=99`、`timeout=0.01/0.05/1.0`、`retries=1/2`）均在本次收紧后的合法范围内。
- 主规格两处措辞与实现不符（`topic` 回显、四步职责顺序），文档两处漂移（日志行描述、`is_sufficient` 表述）。

## Goals / Non-Goals

**Goals:**

- 把 `MAX_ROUNDS = 2` 从"默认值"升级为"构造期即被强制的不变量"：构造参数只可调低，不可调高。
- 把所有构造参数的类型/取值错误收敛到构造期，统一抛 `ValueError`，且不产生任何检索副作用。
- 让规格措辞与实现行为一致（`topic` 规范化回显、逐轮职责顺序），文档描述与日志实际输出一致。
- 对外 HTTP 行为零变化：200/400/422、五段式响应、URL 去重、失败降级一律不动。

**Non-Goals:**

- 不处理 D-7（同步实现被兜底 `except` 静默降级）、D-8（非字符串关键词抛 `AttributeError`）、F-2（零宽空格主题）。
- 不校验 `sufficiency_threshold`，不新增依赖，不改动 `run()` 的编排结构与日志行内容。
- 不做真实网络检索或真实 LLM 调用。

## Decisions

### D1：上限校验放在 `__init__`，而不是 `run()` 或静默收敛

- **选择**：`ResearchEngine.__init__` 在 `max_rounds > MAX_ROUNDS` 时抛 `ValueError`。
- **备选 1：`run()` 内 `min(max_rounds, MAX_ROUNDS)` 静默收敛** —— 否决。调用方以为配置生效、实际被悄悄改写，缺陷被掩盖；本次变更的目的恰恰是让越界配置显式失败。
- **备选 2：在 `run()` 抛出 `ValueError`** —— 否决。配置错误应在最早时机暴露；构造期抛错才能让测试只构造不运行即可覆盖，也避免"服务已启动、首个请求才 500"。
- **影响**：`ResearchEngine(svc, max_rounds=5)` 由"跑 5 轮"变为"构造即失败"。这是本次唯一的 BREAKING 点，仅影响进程内构造调用方，HTTP 契约不变。

### D2：校验顺序与语义 —— 类型 → 下限 → 上限

- 校验顺序：先判类型（整数），再判 `>= 1`，最后判 `<= MAX_ROUNDS`。顺序只影响报错文案，不影响可观察行为。
- 类型判断使用 `isinstance(value, int)`：规格要求"非整数（如 `1.5`）抛 `ValueError`"，未要求拒绝 `bool`。`bool` 是 `int` 子类，实现若额外用 `not isinstance(value, bool)` 收紧亦可，两种写法对规格中的全部 Scenario 等价；该边界不作为规格要求，测试不覆盖。
- 校验通过后 `_max_rounds ∈ [1, MAX_ROUNDS]`，`for round_index in range(self._max_rounds)` 的**结构性保证**不变——上限依旧由 `range` 在进入循环前固定，本次只是给该结构加了一道构造期闸门。

### D3：统一用 `ValueError`，不用 `TypeError`

- 既有 `max_rounds < 1` 已抛 `ValueError`，且既有测试断言 `ValueError`；新增的类型错误若抛 `TypeError` 会让错误类型契约分裂（`1.5` 与 `0` 走不同异常）。
- 规格侧统一写成"抛出 `ValueError`"，实现与测试都只依赖这一种类型。

### D4：`timeout` 用 `math.isfinite` 单点判定"有限正数"

- 现状 `timeout <= 0` 对 `NaN` 为 `False`（NaN 与任何数比较均为 `False`），因此 `NaN` 漏网；`Inf` 则"通过"且实际永不等超时，语义上无效。
- 选择 `isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and math.isfinite(timeout) and timeout > 0`：一次判掉非数值类型、`NaN`、`±Inf`、`0` 与负数，避免用 `0 < t < inf` 这类链式比较（NaN 下同样为 `False`，易误判）。
- `retries` 与 `max_rounds` 同构：`isinstance(retries, int)` 且 `>= 0`。

### D5：规格措辞修改零代码改动，文档修正单独成任务

- `research-api` 的 `topic` 回显：实现已 `.strip()`，本次只改规格文字并补一个 Scenario；不新增行为。
- `research-engine` 的四步职责顺序：实现已是逐轮调用（`generate_keywords` → 每关键词 `search`/`summarize` → 本轮末 `is_sufficient`），本次把读法写死，排除"先全部检索、再统一汇总"的歧义。
- D-4/D-5 文档漂移修正落在 `docs/architecture.md` 与 `README.md`：日志描述改为"充分时输出 `sufficient=true`，另有 `round=N done sections=.. unique_sources=..` 行"；`is_sufficient` 表述改为"不读取**流程累积状态**，阈值来自**构造配置**"。

## Risks / Trade-offs

- [既有 43 个测试回归] → 测试中现有构造取值全部合法；新增用例独立成函数，不改动既有断言；收尾以 `pytest -q` 全绿为验收条件。
- [调用方仍按 `max_rounds>2` 构造] → 这是本次刻意引入的 fail-fast；proposal 已标 BREAKING，且 `ValueError` 文案包含实际值，便于定位。
- [`NaN`/`Inf` 判定遗漏（例如只补 `NaN` 漏 `Inf`）→ 用 `math.isfinite` 单点判断，Scenario 同时覆盖 `nan`、`inf`，测试逐值断言。
- [规格与实现再次漂移] → 本次 delta 的每个 Scenario 都写成可用 pytest 直接验证的形式（含构造期异常断言），tasks 中要求逐条对应测试。

## Migration Plan

- 无数据迁移、无接口迁移；变更仅收紧进程内构造期校验与文档表述。
- 部署即生效：服务启动时 `get_engine()` 使用默认 `max_rounds=MAX_ROUNDS`，不受影响。
- 回滚：还原 `app/engine.py`、`app/services.py` 的构造函数与文档即可，无状态残留。
