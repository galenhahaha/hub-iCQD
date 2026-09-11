# use-free-search

## Why

Bocha 真实搜索需要账户余额，不适合低频面试练习。当前项目的 LLM 真实调用已经可用，因此将默认搜索提供商切换为无需 API Key 的 DuckDuckGo HTML 搜索，避免为了验证 Demo 产生固定充值成本。

## What Changes

- 新增 `DuckDuckGoSearchService`，使用公开 HTML 搜索结果并解析标题、最终 URL 和摘要。
- `RESEARCH_MODE=real` 默认使用 DuckDuckGo；通过 `SEARCH_PROVIDER=bocha` 仍可选择 Bocha。
- Bocha 密钥改为仅在选择 Bocha 时必需，DuckDuckGo 模式只需要 LLM 密钥。
- 测试进程强制使用 Mock，保证即使本地 `.env` 是真实模式也不会联网或消耗额度。
- 更新 README、架构说明和环境变量模板。

## 非目标

- 不承诺免费搜索的生产级稳定性、固定配额或完整网页正文抓取。
- 不移除已有 Bocha 适配器。

## 影响范围

- `app/services.py`、`app/config.py`、`app/main.py`
- `requirements.txt`、`.env.example`、`README.md`、`docs/architecture.md`
- `conftest.py` 与本变更的 OpenSpec 规格
