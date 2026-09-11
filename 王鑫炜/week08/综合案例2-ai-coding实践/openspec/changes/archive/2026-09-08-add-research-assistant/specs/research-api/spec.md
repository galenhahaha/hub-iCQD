## Purpose

定义 `POST /api/research` 的 HTTP 契约：请求校验、成功响应结构与资料不足时的稳定响应，供调用方（前端或其他服务）按固定结构消费研究结果。

## ADDED Requirements

### Requirement: 研究接口生成研究报告

系统 SHALL 提供 `POST /api/research`，接受 JSON 请求体 `{"topic": "<研究主题>"}`，并在主题有效时返回 HTTP 200 与研究报告。

#### Scenario: 正常主题生成报告

- **GIVEN** 请求体为 `{"topic": "主流 Agent 框架对比"}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 200
- **THEN** 响应体为合法 JSON 对象

#### Scenario: 报告结构符合五段式契约

- **GIVEN** 主题为有效主题且研究流程已完成
- **WHEN** 客户端读取响应体
- **THEN** 响应体包含 `topic`、`summary`、`sections`、`sources`、`process` 五个字段
- **THEN** `topic` 为字符串并回显请求中的主题
- **THEN** `summary` 为非空字符串
- **THEN** `sections` 为数组，每个元素含字符串字段 `keyword` 与 `content`
- **THEN** `sources` 为数组，每个元素含字符串字段 `title` 与 `url`
- **THEN** `process` 含字符串数组字段 `keywords` 与整数字段 `rounds`

### Requirement: 空主题被拒绝

系统 SHALL 在 `topic` 为空字符串、仅含空白字符或缺失时返回 HTTP 400，且不执行任何检索。

#### Scenario: 空字符串主题

- **GIVEN** 请求体为 `{"topic": ""}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 400

#### Scenario: 全空白主题

- **GIVEN** 请求体为 `{"topic": "   \t\n "}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 400

#### Scenario: 缺失主题字段

- **GIVEN** 请求体为 `{}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 400

#### Scenario: 400 响应不触发检索

- **GIVEN** 检索服务被注入一个记录调用次数的桩实现
- **WHEN** 客户端以全空白主题调用 `POST /api/research`
- **THEN** 响应状态码为 400
- **THEN** 该桩实现记录的检索调用次数为 0

### Requirement: 资料不足时返回稳定响应

系统 SHALL 在全部检索均无可用资料或检索失败时仍返回 HTTP 200 与结构完整的报告，不得返回 5xx 或因未捕获异常中断。

#### Scenario: 全部检索无结果

- **GIVEN** 检索服务对任何关键词都返回空结果
- **WHEN** 客户端以有效主题调用 `POST /api/research`
- **THEN** 响应状态码为 200
- **THEN** `sections` 为空数组
- **THEN** `sources` 为空数组
- **THEN** `summary` 为非空字符串，说明资料不足

#### Scenario: 单次检索失败不导致 5xx

- **GIVEN** 检索服务在部分关键词上抛出异常
- **WHEN** 客户端以有效主题调用 `POST /api/research`
- **THEN** 响应状态码为 200
- **THEN** 响应体仍包含 `topic`、`summary`、`sections`、`sources`、`process` 五个字段

### Requirement: 响应契约向后兼容

系统 SHALL NOT 移除或重命名五段式契约中的既有字段；如需补充过程细节，MUST 以新增可选字段的形式提供。

#### Scenario: 附加过程字段不破坏既有契约

- **GIVEN** 实现向 `process` 增加记录每轮关键词的可选字段
- **WHEN** 客户端读取响应体
- **THEN** `process.keywords` 仍为字符串数组
- **THEN** `process.rounds` 仍为整数
- **THEN** 响应中仍存在 `topic`、`summary`、`sections`、`sources`、`process`
