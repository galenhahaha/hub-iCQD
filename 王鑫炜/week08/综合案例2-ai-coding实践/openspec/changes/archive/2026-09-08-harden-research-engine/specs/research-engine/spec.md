## MODIFIED Requirements

### Requirement: 研究流程按四步职责编排

系统 SHALL 将整体研究流程封装为单一编排组件，并至少提供关键词生成、检索、结果汇总、资料充分性判断四项职责，由流程按固定顺序调用。该顺序 SHALL 按**轮**组织：每一轮先生成本轮关键词，再对本轮每个关键词依次执行检索与汇总，最后基于本轮汇总结果判断资料是否充分；MUST NOT 被理解为"先执行全部轮次的检索、再统一汇总"的分阶段顺序。

#### Scenario: 流程按固定顺序执行职责

- **GIVEN** 主题为有效主题
- **WHEN** 执行研究流程
- **THEN** 先依据主题生成关键词
- **THEN** 再对每个关键词执行检索
- **THEN** 每个关键词的检索之后紧接该关键词的汇总
- **THEN** 最后基于汇总结果判断资料是否充分

#### Scenario: 职责顺序按轮组织而非分阶段

- **GIVEN** 主题为有效主题且第一轮资料被判定为不充分
- **WHEN** 执行研究流程
- **THEN** 第一轮的充分性判断发生在第一轮全部检索与汇总之后、第二轮任何检索之前
- **THEN** 第二轮先重新生成关键词，再执行该轮的检索与汇总

### Requirement: 最多两轮检索

系统 SHALL 最多执行两轮检索；该上限 MUST 由流程结构保证，不得依赖事后计数判断，且不得出现无限循环。该上限 MUST NOT 被构造参数突破：`MAX_ROUNDS = 2` 是绝对上限，构造参数 `max_rounds` 只可调低（用于测试单轮路径），调高 MUST 在校验期被拒绝。

#### Scenario: 资料充分时只执行一轮

- **GIVEN** 第一轮检索结果被判定为充分
- **WHEN** 执行研究流程
- **THEN** `process.rounds` 为 1
- **THEN** 不执行第二轮检索

#### Scenario: 资料不足时执行补充检索

- **GIVEN** 第一轮检索结果被判定为不充分
- **WHEN** 执行研究流程
- **THEN** 执行第二轮补充检索
- **THEN** `process.rounds` 为 2

#### Scenario: 充分性判断恒为不充分也不超过两轮

- **GIVEN** 充分性判断对任何输入都返回"不充分"
- **WHEN** 执行研究流程
- **THEN** 实际检索轮次不超过 2
- **THEN** 流程正常结束并返回报告

#### Scenario: 构造参数调高被拒绝

- **GIVEN** 构造编排组件时传入的 `max_rounds` 大于 2
- **WHEN** 执行构造
- **THEN** 抛出 `ValueError`
- **THEN** 不执行任何检索调用

#### Scenario: 构造参数调低到 1 时只执行一轮

- **GIVEN** 构造编排组件时传入 `max_rounds=1`，且充分性判断对任何输入都返回"不充分"
- **WHEN** 执行研究流程
- **THEN** `process.rounds` 为 1
- **THEN** 不执行第二轮检索

## ADDED Requirements

### Requirement: 构造参数校验

系统 SHALL 在构造研究流程编排组件与其检索包装组件时校验构造参数，非法取值 MUST 在构造期抛出 `ValueError`，MUST NOT 推迟到流程执行或检索调用时才报错。整数参数 MUST 为整数类型；`retries` MUST 为非负整数；`timeout` MUST 为有限正数。

#### Scenario: max_rounds 超过上限

- **GIVEN** 构造编排组件时传入 `max_rounds=3`
- **WHEN** 执行构造
- **THEN** 抛出 `ValueError`
- **THEN** 不执行任何检索调用

#### Scenario: max_rounds 低于下限

- **GIVEN** 构造编排组件时分别传入 `max_rounds=0` 与 `max_rounds=-1`
- **WHEN** 执行构造
- **THEN** 两种情况均抛出 `ValueError`

#### Scenario: max_rounds 非整数

- **GIVEN** 构造编排组件时传入 `max_rounds=1.5`
- **WHEN** 执行构造
- **THEN** 抛出 `ValueError`（而非推迟到流程执行时抛出 `TypeError`）

#### Scenario: retries 为负

- **GIVEN** 构造检索包装组件时传入 `retries=-1`
- **WHEN** 执行构造
- **THEN** 抛出 `ValueError`

#### Scenario: retries 非整数

- **GIVEN** 构造检索包装组件时传入 `retries=1.5`
- **WHEN** 执行构造
- **THEN** 抛出 `ValueError`

#### Scenario: timeout 非有限

- **GIVEN** 构造检索包装组件时分别传入 `timeout=float("nan")` 与 `timeout=float("inf")`
- **WHEN** 执行构造
- **THEN** 两种情况均抛出 `ValueError`

#### Scenario: timeout 非正

- **GIVEN** 构造检索包装组件时分别传入 `timeout=0` 与 `timeout=-1`
- **WHEN** 执行构造
- **THEN** 两种情况均抛出 `ValueError`
