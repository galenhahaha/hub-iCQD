# research-engine Specification

## Purpose
定义研究流程的编排行为：关键词生成、检索与汇总、充分性判断、检索轮数硬上限、来源去重与检索失败容错，使研究过程可复现、有确定的停止条件且外部依赖可替换。

## Requirements

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

### Requirement: 关键词生成可复现

系统 SHALL 依据主题生成至少一个非空检索关键词，且同一主题重复生成得到相同的关键词序列。

#### Scenario: 有效主题生成关键词

- **GIVEN** 主题为 "主流 Agent 框架对比"
- **WHEN** 生成检索关键词
- **THEN** 返回至少一个非空关键词
- **THEN** 重复以同一主题生成关键词得到完全相同的序列

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

### Requirement: 真实服务可配置接入

系统 SHALL 支持通过环境变量显式启用真实网页搜索和 OpenAI Chat Completions 兼容大模型，同时保留默认离线 Mock 模式。真实服务适配器 MUST 通过依赖注入接入研究引擎，且不得把 API Key 写入源码。真实搜索提供商 SHALL 支持无需 API Key 的 DuckDuckGo，Bocha 仅在显式选择时需要余额和密钥。

#### Scenario: 默认模式不依赖外部服务

- **GIVEN** 未设置 `RESEARCH_MODE=real`
- **WHEN** 启动并调用研究接口
- **THEN** 系统使用本地 Mock 搜索和确定性逻辑
- **THEN** 不发起外部网络请求

#### Scenario: 真实模式默认使用免费搜索

- **GIVEN** 设置 `RESEARCH_MODE=real`、未设置 `SEARCH_PROVIDER` 且配置有效的 LLM 密钥
- **WHEN** 执行研究流程
- **THEN** 系统使用 DuckDuckGo 网页搜索和配置的 LLM
- **THEN** 不要求 `BOCHA_API_KEY`

#### Scenario: 真实模式可选 Bocha

- **GIVEN** 设置 `RESEARCH_MODE=real`、`SEARCH_PROVIDER=bocha` 且配置有效的 Bocha 与 LLM 密钥
- **WHEN** 执行研究流程
- **THEN** 搜索结果来自 Bocha
- **THEN** 关键词、总结、充分性判断或报告摘要可以由配置的 LLM 生成

#### Scenario: 真实模式使用配置的外部服务

- **GIVEN** 设置 `RESEARCH_MODE=real` 且配置有效的搜索与 LLM 密钥
- **WHEN** 执行研究流程
- **THEN** 关键词、总结、充分性判断或报告摘要可以由配置的 LLM 生成
- **THEN** 搜索结果来自配置的网页搜索服务

#### Scenario: 真实配置缺失时快速失败

- **GIVEN** 设置 `RESEARCH_MODE=real` 但缺少 LLM 密钥，或选择 `SEARCH_PROVIDER=bocha` 但缺少 Bocha 密钥
- **WHEN** 系统装配真实服务
- **THEN** 返回包含缺失变量名称的明确配置错误
- **THEN** 不以 Mock 结果伪装真实研究

#### Scenario: 模型调用失败时保持流程稳定

- **GIVEN** 真实 LLM 调用超时、返回空内容或无法解析
- **WHEN** 研究流程继续执行
- **THEN** 系统回退到确定性逻辑或返回稳定的资料不足结果
- **THEN** 不向 API 响应暴露密钥或完整授权信息

### Requirement: 真实搜索摘要可供模型使用

系统 SHALL 将真实搜索结果的标题、URL 和摘要传递给总结模型，同时保持既有响应中的 `title` / `url` 字段契约不变。

#### Scenario: 搜索摘要进入总结上下文

- **GIVEN** Bocha 返回标题、URL 和摘要
- **WHEN** 生成关键词对应的正文段落
- **THEN** LLM 适配器收到该关键词及搜索摘要
- **THEN** 对外来源仍只暴露既有的标题和 URL 字段

### Requirement: 免费搜索结果可供模型使用

系统 SHALL 将 DuckDuckGo 返回的标题、最终 URL 和摘要传递给总结模型，同时保持既有响应中的 `title` / `url` 字段契约不变。免费搜索异常、限流或页面结构变化 SHALL 经由统一容错链路降级为空结果。

#### Scenario: DuckDuckGo 搜索结果进入总结上下文

- **GIVEN** DuckDuckGo 返回标题、重定向 URL 和摘要
- **WHEN** 生成关键词对应的正文段落
- **THEN** LLM 适配器收到该关键词及搜索摘要
- **THEN** 对外来源仍只暴露既有的标题和 URL 字段

#### Scenario: 免费搜索失败不导致接口 5xx

- **GIVEN** DuckDuckGo 请求超时、限流或返回不可解析页面
- **WHEN** 客户端调用研究接口
- **THEN** 搜索服务按重试策略处理并最终降级为空结果
- **THEN** 接口仍返回结构完整的 HTTP 200 研究报告
