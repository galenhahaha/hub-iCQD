## Why

当前研究助手只使用确定性的本地 Mock，能够验证 Workflow、依赖注入和测试，但不能完成真实研究。需要在不破坏离线测试的前提下接入真实网页搜索和 OpenAI 兼容大模型，让用户可以通过配置启用真实模式。

## What Changes

- 新增可配置的 `mock` / `real` 双运行模式，默认仍为离线 Mock。
- 新增 Bocha 网页搜索适配器，保留搜索摘要供模型总结，并复用超时、重试和降级包装。
- 新增 OpenAI Chat Completions 兼容的 LLM 适配器，用于关键词生成、资料总结、充分性判断和报告摘要。
- 通过 `.env` / 环境变量读取 API Key，新增 `.env.example`，不在源码中保存密钥。
- 保持现有 HTTP 响应契约、Workflow 轮次上限、依赖注入边界和离线测试能力。
- 更新 README、CLAUDE.md 和架构文档，说明真实模式的配置和限制。

## Non-Goals

- 不实现网页全文抓取、引用级事实绑定、前端、数据库或任务队列。
- 不把真实服务强制设为默认模式，不让测试依赖网络或外部 API。
- 不保存、打印或提交任何 API Key。

## Impact

- 新增 `app/config.py`、`app/llm.py` 和真实 `BochaSearchService`。
- `ResearchEngine` 增加可选 LLM 能力注入；模型失败时回退到确定性逻辑。
- 需要新增 `openai` 和 `python-dotenv` 依赖。
