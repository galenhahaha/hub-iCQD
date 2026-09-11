## MODIFIED Requirements

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

## ADDED Requirements

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
