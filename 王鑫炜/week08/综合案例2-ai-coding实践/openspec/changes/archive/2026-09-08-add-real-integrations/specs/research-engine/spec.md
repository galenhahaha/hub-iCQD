## ADDED Requirements

### Requirement: 真实服务可配置接入

系统 SHALL 支持通过环境变量显式启用真实网页搜索和 OpenAI Chat Completions 兼容大模型，同时保留默认离线 Mock 模式。真实服务适配器 MUST 通过依赖注入接入研究引擎，且不得把 API Key 写入源码。

#### Scenario: 默认模式不依赖外部服务

- **GIVEN** 未设置 `RESEARCH_MODE=real`
- **WHEN** 启动并调用研究接口
- **THEN** 系统使用本地 Mock 搜索和确定性逻辑
- **THEN** 不发起外部网络请求

#### Scenario: 真实模式使用配置的外部服务

- **GIVEN** 设置 `RESEARCH_MODE=real` 且配置有效的 Bocha 与 LLM 密钥
- **WHEN** 执行研究流程
- **THEN** 关键词、总结、充分性判断或报告摘要可以由配置的 LLM 生成
- **THEN** 搜索结果来自配置的网页搜索服务

#### Scenario: 真实配置缺失时快速失败

- **GIVEN** 设置 `RESEARCH_MODE=real` 但缺少任一必需密钥
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
