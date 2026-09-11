# 架构说明与改进方向

本文说明研究助手的模块边界、Mock/真实双模式、关键设计落点，以及后续可演进的方向。代码位置均以 `app/` 为准。

## 模块划分

```text
app/
├── models.py       # 请求/响应契约 + 领域 DTO（SearchResult、RoundDetail）
├── services.py     # SearchService + Mock/DuckDuckGo/Bocha + 重试包装
├── llm.py          # LLMService + OpenAICompatibleLLMService
├── config.py       # 环境变量、模式和真实服务配置校验
├── engine.py       # ResearchEngine：Workflow 控制 + Agent 式判断 + 汇总去重
└── main.py         # FastAPI 路由、400 校验、模式装配
tests/test_research.py
```

| 模块 | 职责 | 不做的事 |
| --- | --- | --- |
| `models.py` | 数据结构与契约 | 不含业务流程、不发 IO |
| `services.py` | 检索能力的抽象、本地 Mock、免费 DuckDuckGo、可选 Bocha、超时/重试包装 | 不知道"轮次""充分性"，不拼装报告 |
| `llm.py` | OpenAI 兼容模型调用、JSON 解析和角色提示词 | 不控制研究循环，不直接操作 HTTP 路由 |
| `config.py` | 真实模式配置和密钥校验 | 不保存密钥，不参与业务流程 |
| `engine.py` | 关键词生成、检索与汇总、充分性判断、轮次控制、URL 去重、报告组装 | 不感知 HTTP、不感知 FastAPI |
| `main.py` | 路由、请求校验与 400、依赖装配 | 不写研究逻辑 |

## 1. Workflow 控制落点：`ResearchEngine.run()`

`app/engine.py` 的 `run()` 是唯一的编排入口，按固定顺序执行四步职责：

```text
generate_keywords()  →  search()  →  summarize()  →  is_sufficient()
     （每轮一次）        （每关键词）    （每关键词）      （每轮末一次）
```

所有"顺序、状态、何时停"都集中在这一个方法里：`sections`、`seen_urls`、`ordered_keywords` 都是局部状态，外部无法从中间插入；单测只需替换注入的检索服务即可覆盖全部分支。

## 2. Agent 式判断落点：`ResearchEngine._is_sufficient()`

这是流程中**唯一**的决策点——引擎拿到本轮资料后自主判断"够不够、要不要再补一轮"。

- Mock 模式使用可重复判据：至少一个非空 `section`，且去重后来源数 `>= sufficiency_threshold`（默认 2）。
- 真实模式将当前段落和来源交给 `LLMService.is_sufficient()` 判断；调用失败时回退到 Mock 判据。
- `run()` 只依赖统一的异步辅助方法，因此真实模型、Mock 和测试桩可以互换。

## 3. 依赖注入边界：`SearchService` 协议

`app/services.py` 用 `typing.Protocol` 定义检索契约（`async def search(keyword) -> List[SearchResult]`）：

- 引擎通过构造函数接收实现（`ResearchEngine(search_service)`），内部**不硬编码** `MockSearchService`；
- `app/main.py` 用 `Depends(get_engine)` → `Depends(get_search_service)` / `Depends(get_llm_service)` 装配；`RESEARCH_MODE=real` 默认注入免费 DuckDuckGo，也可通过 `SEARCH_PROVIDER=bocha` 切换 Bocha；默认注入 Mock；
- 测试用 `app.dependency_overrides[get_search_service]` 注入桩，无需继承任何基类（结构化子类型）；
- `ResilientSearchService` 实现同一协议，对引擎完全透明——它只包在外部服务边界上，超时/重试耗尽后抛 `SearchError`，由 `ResearchEngine.search()` 统一降级为空结果。

因此切换真实服务不需要改动 Workflow；只需配置环境变量或替换依赖装配。

## 4. 两轮停止条件的结构性说明

```python
MAX_ROUNDS = 2   # 模块级常量，同时是构造函数默认值

for round_index in range(self._max_rounds):   # 迭代次数在进入循环前就被 range 固定
    ...
    if self.is_sufficient(...):               # break 只用于"提前结束"
        break
```

- 用 `for ... in range(2)` 而非 `while` + 手动自增：循环体执行次数由 `range` 对象在构造时确定，**物理上不可能出现第三轮**，即使 `is_sufficient` 永远返回 `False`、即使轮次计划被错误修改。
- `break` 只负责提前结束，不承担"控制上限"的职责，因此不存在"计数器写漏导致多跑一轮"的风险。
- `_max_rounds` 在构造期做下限校验（`< 1` 抛 `ValueError`），避免被误设为 0 或负数。
- `process.rounds` 取自实际执行轮次（`len(rounds_detail)`），与上限解耦：充分时 1，不充分时 2。

## 5. 过程可追溯

引擎逐轮维护 `RoundDetail(round, keywords)` 并写入结构化日志：

- `round=N keywords=...`：本轮生成的关键词列表；
- `round=N keyword='...' results=M`：本轮每个关键词的检索结果数（某关键词无可用资料时，改为输出 `round=N keyword='...' results=0 无可用资料，跳过其汇总条目`）；
- `round=N done sections=.. unique_sources=..`：本轮结束时的汇总条目数与去重来源数；
- `round=N sufficient=true`：**仅在本轮判定资料充分时输出**，不充分时不输出该行（流程继续下一轮，到达轮次上限后自然结束）。

`process.rounds_detail` 作为**可选**附加字段暴露每轮关键词；`process.keywords`（字符串数组）与 `process.rounds`（整数）的名称与类型保持不变，属向后兼容的超集。

## 6. 运行模式与外部调用

```text
RESEARCH_MODE=mock
  main.py → MockSearchService → ResearchEngine（本地确定性逻辑）

RESEARCH_MODE=real
  main.py → ResilientSearchService(DuckDuckGoSearchService)
          → OpenAICompatibleLLMService
          → ResearchEngine（真实搜索 + 真实模型）
```

真实模式的模型密钥只从 `.env` 或环境变量读取。DuckDuckGo 不需要搜索密钥；可选的 `BochaSearchService` 仍保留搜索摘要到 `SearchResult` 的私有字段，免费适配器也使用相同的摘要字段，因此不会改变现有 API 的响应契约。

## 7. 改进方向

1. **并行检索**：当前逐关键词串行 `await`；签名已全链路异步，可用 `asyncio.gather` 并行化并加并发上限，不改变任何对外签名。
2. **网页全文阅读**：当前搜索适配器使用搜索摘要；可增加页面抓取、正文提取和分块后再交给 LLM。
3. **真实引用绑定**：让每个结论携带对应 URL，而不是只返回全局来源列表。
4. **模型可观测性**：记录请求耗时、Token、模型错误和回退次数，但不要记录密钥或完整敏感 Prompt。
5. **并行检索与限流**：用 `asyncio.gather` 并行查询，并添加并发上限、缓存和费用控制。
6. **持久化和任务队列**：将同步 API 升级为后台任务、数据库和可恢复状态。

## 当前非目标

不引入前端、数据库、用户系统、MCP、多 Agent SDK、网页全文抓取和生产级任务队列。真实模式已经接入外部搜索和 LLM，但仍是教学级原型。
