## MODIFIED Requirements

### Requirement: 研究接口生成研究报告

系统 SHALL 提供 `POST /api/research`，接受 JSON 请求体 `{"topic": "<研究主题>"}`，并在主题有效时返回 HTTP 200 与研究报告。报告可以来自默认的离线 Mock 流程，也可以来自通过环境变量启用的真实搜索与 LLM 流程；两种模式 SHALL 保持相同的 HTTP 响应结构。

#### Scenario: Mock 与真实模式共享响应契约

- **GIVEN** 分别在 `mock` 和有效 `real` 配置下提交同一有效主题
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 两种模式均返回 `topic`、`summary`、`sections`、`sources`、`process` 五个字段
- **THEN** `sources` 中每项仍包含字符串字段 `title` 与 `url`

#### Scenario: 正常主题生成报告

- **GIVEN** 请求体为 `{"topic": "主流 Agent 框架对比"}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 200
- **THEN** 响应体为合法 JSON 对象

#### Scenario: 报告结构符合五段式契约

- **GIVEN** 主题为有效主题且研究流程已完成
- **WHEN** 客户端读取响应体
- **THEN** 响应体包含 `topic`、`summary`、`sections`、`sources`、`process` 五个字段
- **THEN** `topic` 为字符串，回显请求主题**规范化（去除首尾空白）后**的结果
- **THEN** `summary` 为非空字符串
- **THEN** `sections` 为数组，每个元素含字符串字段 `keyword` 与 `content`
- **THEN** `sources` 为数组，每个元素含字符串字段 `title` 与 `url`
- **THEN** `process` 含字符串数组字段 `keywords` 与整数字段 `rounds`

#### Scenario: 主题首尾空白被规范化后回显

- **GIVEN** 请求体为 `{"topic": "  主题  "}`
- **WHEN** 客户端调用 `POST /api/research`
- **THEN** 响应状态码为 200
- **THEN** 响应体的 `topic` 为 `"主题"`（已去除首尾空白）
