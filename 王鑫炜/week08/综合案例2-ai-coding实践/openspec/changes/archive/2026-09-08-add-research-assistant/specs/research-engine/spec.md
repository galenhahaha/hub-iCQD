## Purpose

定义研究流程的编排行为：关键词生成、检索与汇总、充分性判断、检索轮数硬上限、来源去重与检索失败容错，使研究过程可复现、有确定的停止条件且外部依赖可替换。

## ADDED Requirements

### Requirement: 研究流程按四步职责编排

系统 SHALL 将整体研究流程封装为单一编排组件，并至少提供关键词生成、检索、结果汇总、资料充分性判断四项职责，由流程按固定顺序调用。

#### Scenario: 流程按固定顺序执行职责

- **GIVEN** 主题为有效主题
- **WHEN** 执行研究流程
- **THEN** 先依据主题生成关键词
- **THEN** 再对每个关键词执行检索
- **THEN** 再对检索结果执行汇总
- **THEN** 最后基于汇总结果判断资料是否充分

### Requirement: 关键词生成可复现

系统 SHALL 依据主题生成至少一个非空检索关键词，且同一主题重复生成得到相同的关键词序列。

#### Scenario: 有效主题生成关键词

- **GIVEN** 主题为 "主流 Agent 框架对比"
- **WHEN** 生成检索关键词
- **THEN** 返回至少一个非空关键词
- **THEN** 重复以同一主题生成关键词得到完全相同的序列

### Requirement: 最多两轮检索

系统 SHALL 最多执行两轮检索；该上限 MUST 由流程结构保证，不得依赖事后计数判断，且不得出现无限循环。

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

### Requirement: 来源 URL 去重

系统 SHALL 对全部轮次收集到的来源按 URL 去重，同一 URL 在 `sources` 中只出现一次，并保留各 URL 首次出现的顺序。

#### Scenario: 跨轮次重复 URL 被去重

- **GIVEN** 第一轮与第二轮检索返回包含相同 URL 的来源
- **WHEN** 生成报告
- **THEN** `sources` 中该 URL 只出现一次
- **THEN** `sources` 的顺序为各 URL 首次出现的顺序

#### Scenario: 同一轮内重复 URL 被去重

- **GIVEN** 同一轮检索结果中包含两个 URL 相同的来源
- **WHEN** 生成报告
- **THEN** `sources` 中该 URL 只出现一次

### Requirement: 检索失败与空结果容错

系统 SHALL 在单个关键词检索抛出异常或返回空结果时跳过该关键词并继续流程，不得中断整体研究。

#### Scenario: 单次检索失败不中断流程

- **GIVEN** 某个关键词的检索抛出异常，其余关键词正常返回结果
- **WHEN** 执行研究流程
- **THEN** 流程正常结束并返回报告
- **THEN** 该失败关键词不产生 `sections` 条目
- **THEN** 其余关键词的汇总结果仍出现在 `sections` 中

#### Scenario: 检索返回空结果

- **GIVEN** 某个关键词的检索返回空结果列表
- **WHEN** 执行研究流程
- **THEN** 该关键词不产生 `sections` 条目
- **THEN** 流程不抛出异常

### Requirement: 每轮关键词可追溯

系统 SHALL 记录每一轮实际使用的关键词，使 `process.keywords` 覆盖所有已执行轮次的关键词且不含重复项。

#### Scenario: 两轮关键词汇总为并集

- **GIVEN** 第一轮使用关键词集合 K1，第二轮使用关键词集合 K2
- **WHEN** 执行两轮研究流程
- **THEN** `process.keywords` 包含 K1 与 K2 中的全部关键词
- **THEN** `process.keywords` 中不出现重复关键词

### Requirement: 检索服务可替换

系统 SHALL 通过抽象接口或依赖注入获取检索能力，使检索实现可在不修改研究流程的前提下被替换或注入测试桩。

#### Scenario: 注入替代检索实现

- **GIVEN** 一个返回预置结果的替代检索实现
- **WHEN** 以该实现构造并执行研究流程
- **THEN** 报告中的 `sections` 与 `sources` 反映该替代实现返回的数据
- **THEN** 研究流程无需修改即可使用该实现
