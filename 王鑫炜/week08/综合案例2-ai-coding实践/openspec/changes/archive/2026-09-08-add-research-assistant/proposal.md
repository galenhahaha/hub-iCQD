## Why

市场或产品人员需要围绕一个主题快速收集资料并形成研究报告，但手工检索与汇总成本高、过程不可复现。本练习要交付的不是"接入真实大模型"，而是一个结构清晰、可测试、可扩展的 Agent 式研究流程：把"生成关键词 → 搜索 → 汇总 → 判断是否充分 → 必要时补一轮 → 出报告"这条链路显式建模，并保证它有确定的停止条件和可替换的外部依赖边界。

## What Changes

- 新增 `POST /api/research` 接口，接收 `{"topic": "..."}`，返回 `topic / summary / sections / sources / process` 五段式报告。
- 新增 `ResearchEngine` 编排整体研究流程，并拆分 `generate_keywords(topic)`、`search(keyword)`、`summarize(keyword, results)`、`is_sufficient(...)` 四个职责。
- 新增搜索服务抽象接口 + 本地确定性模拟实现，使搜索能力可通过依赖注入替换为真实服务，测试中可注入桩实现。
- 输入校验：`topic` 为空或仅含空白字符（含字段缺失）返回 HTTP 400。
- 来源 URL 去重：跨轮次收集的来源按 URL 去重，保留首次出现顺序。
- 研究循环硬上限：最多两轮检索，且该上限由结构（受控循环/枚举）保证，而非依赖计数器事后判断。
- 失败与空结果降级：单次搜索抛异常或返回空列表时不崩溃，跳过该关键词并继续出报告；全部搜索无结果时仍返回 200 与说明性摘要。
- 新增 `tests/test_research.py`，覆盖 README 第 5 节要求的 5 个场景。
- 在 `README.md` 补充安装、启动与测试命令。

## Capabilities

### New Capabilities

- `research-api`: `POST /api/research` 的 HTTP 契约——请求校验、成功响应结构（`topic/summary/sections/sources/process`）、400 与降级响应等外部可观察行为。
- `research-engine`: 研究流程编排行为——关键词生成、搜索与汇总职责、充分性判断、两轮硬上限、URL 去重、单次搜索失败的容错。

### Modified Capabilities

无。本仓库 `openspec/specs/` 目前为空（仅有 `.gitkeep`），本次全部为新增能力。

## Impact

- 新增文件：`app/__init__.py`、`app/main.py`、`app/engine.py`、`app/models.py`、`app/services.py`、`tests/test_research.py`、`requirements.txt`。
- 修改文件：`README.md`（仅追加安装/启动/测试命令，不改动需求描述）。
- 依赖：`fastapi`、`uvicorn`、`pydantic`、`pytest`、`httpx`（供 `TestClient` 使用）。
- 不涉及：前端、数据库、用户系统、部署、MCP、多 Agent SDK、真实网络搜索与真实 LLM 调用。
- 不在代码、日志或提交记录中存放任何密钥。

## 假设（细节歧义的处理）

以下为不影响需求范围、但会落到实现与验收细节的假设；若与预期不符请指出，再调整 spec。

1. **关键词与搜索均为本地确定性实现**：同一 `topic` 每次运行产生相同的关键词序列与相同搜索结果，保证测试可预测、不依赖网络。
2. **`process` 字段语义**：`process.keywords` 为所有已执行轮次关键词的**有序去重并集**；`process.rounds` 为**实际执行的轮数**（1 或 2），不等于上限 2。
3. **`topic` 校验边界**：字段缺失、`null`、空字符串或全空白字符串均视为"空主题"并返回 400；非字符串类型（如数字、数组）由 Pydantic 返回 422。README 只对空/全空白规定了 400，故其余情况沿用框架默认校验语义。
4. **`sources` 语义**：汇总所有轮次实际搜索到的来源，按 URL 去重并保留首次出现顺序；不做可用性探测。
5. **空结果与失败降级**：搜索返回空列表或抛异常都视为"该关键词无可用资料"，跳过其 `sections` 条目；全部关键词都无资料时仍返回 200，`sections` 与 `sources` 为空数组，`summary` 给出"资料不足"的说明文字。
6. **加分项的落点**：README 第 8 节"记录每一轮的关键词和执行过程"通过**结构化日志 + `process` 的可选附加字段**实现，`process.keywords`、`process.rounds` 等第 3 节字段名与类型保持不变，属向后兼容的超集；核心验收只断言第 3 节字段。
7. **目录结构**：沿用 README 第 6 节建议的 `app/` + `tests/` 布局，不额外引入分层目录。
