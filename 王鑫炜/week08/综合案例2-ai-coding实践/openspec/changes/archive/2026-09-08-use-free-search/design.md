# 设计说明

## 搜索提供商选择

`SEARCH_PROVIDER` 支持 `duckduckgo` 和 `bocha`。真实模式下由 `main.py` 根据配置创建对应实现，再统一包裹 `ResilientSearchService`；`ResearchEngine` 只依赖 `SearchService` 协议，不感知提供商。

## DuckDuckGo 适配器

`DuckDuckGoSearchService` 使用 `httpx.AsyncClient` 请求 `https://html.duckduckgo.com/html/`，通过 `lxml` 解析 `result__a` 和 `result__snippet` 节点。搜索结果的重定向链接从 `uddg` 参数还原为最终 URL，并将摘要保存到 `SearchResult` 的私有字段。

公开 HTML 页面无需搜索 API Key，但可能受到限流或页面结构变化影响；网络异常由现有超时、重试和降级链路处理。

## 配置校验

`real_config()` 始终校验 LLM Key；只有 `SEARCH_PROVIDER=bocha` 时才校验 `BOCHA_API_KEY`。搜索数量、超时和重试参数继续共享原有配置。

## 测试隔离

根 `conftest.py` 在 pytest 进程中强制设置 `RESEARCH_MODE=mock`，防止开发者本地 `.env` 的真实配置让单元测试触发外部请求。真实链路使用手动集成验证。
