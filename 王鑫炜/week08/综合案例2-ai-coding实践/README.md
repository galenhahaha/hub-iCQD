# AI Coding 实践题：简易研究助手

## 1. 业务背景

市场或产品人员经常需要围绕一个主题收集资料并形成研究报告。请实现一个简易研究助手：用户输入研究主题，系统生成检索关键词，调用搜索服务获取资料，整理成报告；如果现有资料不足，可以补充检索一次。

项目支持两种运行模式：默认 Mock 模式用于离线测试；设置 `RESEARCH_MODE=real` 后，会接入免费 DuckDuckGo 搜索和 OpenAI Chat Completions 兼容的大模型（默认配置为 DeepSeek）。也可以把 `SEARCH_PROVIDER` 改为 `bocha` 使用 Bocha，但这需要账户余额。

## 2. 核心流程

```text
生成关键词
  -> 搜索资料
  -> 汇总内容
  -> 判断资料是否充分
  -> 必要时补充检索一次
  -> 生成报告
```

## 3. API 要求

使用 Python、FastAPI 和 Pydantic 实现：

```http
POST /api/research
Content-Type: application/json

{
  "topic": "主流 Agent 框架对比"
}
```

成功响应示例：

```json
{
  "topic": "主流 Agent 框架对比",
  "summary": "研究摘要",
  "sections": [
    {
      "keyword": "LangGraph",
      "content": "根据搜索结果生成的总结"
    }
  ],
  "sources": [
    {
      "title": "资料标题",
      "url": "https://example.com"
    }
  ],
  "process": {
    "keywords": ["LangGraph", "OpenAI Agents SDK"],
    "rounds": 1
  }
}
```

## 4. 功能要求

1. 将整体研究流程封装为 `ResearchEngine`。
2. 至少拆分以下职责：
   - `generate_keywords(topic)`：生成检索关键词；
   - `search(keyword)`：通过抽象接口获取搜索结果；
   - `summarize(keyword, results)`：整理某个关键词的搜索结果；
   - `is_sufficient(...)`：判断资料是否充分。
3. 最多执行两轮检索，禁止无限循环。
4. 来源 URL 必须去重。
5. `topic` 为空或只有空白字符时返回 HTTP 400。
6. 搜索没有结果或单次搜索失败时，程序不能直接崩溃，应返回合理结果或错误信息。
7. 默认使用本地模拟实现；真实模式默认使用无需 API Key 的 DuckDuckGo，也可通过环境变量切换搜索服务提供商。
8. 不得在代码中写入 API Key。

## 5. 测试要求

至少覆盖：

- 正常输入能够生成报告；
- 空主题返回 HTTP 400；
- 重复 URL 被正确去重；
- 研究循环不会超过两轮；
- 搜索无结果时系统仍能稳定响应。

## 6. 建议目录

```text
app/
├── __init__.py
├── main.py
├── config.py
├── engine.py
├── llm.py
├── models.py
└── services.py
tests/
└── test_research.py
README.md
requirements.txt
```

可以在理由充分的情况下调整目录结构。

## 7. 完成标准

- 服务能够本地启动；
- API 行为满足需求；
- 自动化测试全部通过；
- README 补充安装、启动和测试命令；
- 代码具有必要的类型标注、异常处理和日志；
- 能够说明 Workflow 与 Agent 决策分别位于代码的什么位置。

## 8. 加分项

- 通过依赖注入替换搜索服务；
- 记录每一轮的关键词和执行过程；
- 合理使用异步函数；
- 为外部服务设计超时、重试或降级策略；
- 提交简短的架构说明和改进方向。

## 9. 安装、启动与测试

> 本机已备好虚拟环境，所有命令请使用 `.venv/bin/` 下的解释器（系统 `python3` 未安装依赖）。

安装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

启动服务：

```bash
.venv/bin/uvicorn app.main:app --reload
```

### 真实模式配置

复制配置模板并填写密钥（不要把 `.env` 提交到 Git）：

```bash
cp .env.example .env
```

编辑 `.env`，至少设置：

```dotenv
RESEARCH_MODE=real
SEARCH_PROVIDER=duckduckgo
LLM_API_KEY=你的模型 API Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

也可以使用 OpenAI 或其他兼容 Chat Completions 的服务，只需修改 `LLM_BASE_URL` 和 `LLM_MODEL`。真实模式的流程是：LLM 生成关键词 → DuckDuckGo 搜索 → LLM 总结 → LLM 判断是否补检 → LLM 生成摘要。

DuckDuckGo 搜索不需要单独的 API Key，但公开搜索可能限流或暂时不可用；如果改用 Bocha，需要设置 `SEARCH_PROVIDER=bocha` 并填写 `BOCHA_API_KEY`。默认 Mock 模式不联网，也不会产生外部费用。

调用接口：

```bash
curl -X POST http://127.0.0.1:8000/api/research \
  -H 'Content-Type: application/json' \
  -d '{"topic":"主流 Agent 框架对比"}'
```

运行测试：

```bash
.venv/bin/pytest -q
```

按需筛选单个场景（对应第 5 节必测项）：

```bash
.venv/bin/pytest -q tests/test_research.py -k normal_report    # 正常输入生成报告
.venv/bin/pytest -q tests/test_research.py -k empty_topic      # 空主题 400
.venv/bin/pytest -q tests/test_research.py -k url_dedup        # URL 去重
.venv/bin/pytest -q tests/test_research.py -k rounds_cap       # 不超过两轮
.venv/bin/pytest -q tests/test_research.py -k search_failure   # 搜索无结果/失败仍稳定响应
```

## 10. Workflow 控制与 Agent 式判断的代码位置

- **Workflow 控制**：`app/engine.py` 的 `ResearchEngine.run()`。顺序（生成关键词 → 检索 → 汇总 → 判断充分性）、状态（已收集的 `sections`/`sources`）与"何时停"全部集中在这一个方法里；轮次上限由 `for round_index in range(self._max_rounds)` 在结构上保证（`MAX_ROUNDS = 2`），`break` 只用于提前结束。
- **Agent 式判断**：`app/engine.py` 的 `_is_sufficient()`。真实模式下注入 `OpenAICompatibleLLMService`，Mock 模式使用可重复的阈值判断；失败时回退阈值规则。
- **真实适配器**：`app/services.py` 的 `DuckDuckGoSearchService`（默认）/ `BochaSearchService`（可选）和 `app/llm.py` 的 `OpenAICompatibleLLMService`，分别负责真实网页搜索和模型调用。
- **依赖注入边界**：检索能力由 `app/services.py` 的 `SearchService`（`typing.Protocol`）定义，LLM 能力由 `app/llm.py` 的 `LLMService` 定义；`app/main.py` 根据 `RESEARCH_MODE` 装配实现，测试用 `app.dependency_overrides` 注入桩实现。
- **完整架构说明与改进方向**：见 [`docs/architecture.md`](docs/architecture.md)。
