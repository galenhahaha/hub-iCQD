## Context

项目当前的 `ResearchEngine` 已经通过 `SearchService` 注入检索能力，但关键词生成、总结和充分性判断仍是本地规则。真实模式应替换外部能力，而不改动核心轮次编排和既有测试。

## Goals / Non-Goals

**Goals:**

- 真实模式由 `RESEARCH_MODE=real` 显式开启。
- Bocha 和 OpenAI 兼容客户端均位于适配器边界，业务流程不感知供应商协议。
- 真实服务失败时仍能在一次请求内安全降级，不泄露密钥。
- Mock 模式保持零网络、可重复和现有测试全绿。

**Non-Goals:**

- 不在本次变更中重写同步 HTTP API 为后台任务。
- 不引入 Agents SDK；LLM 角色由一个轻量的 Chat Completions 适配器实现。

## Decisions

### D1：通过模式开关选择 Mock 或真实实现

`app/main.py` 根据 `RESEARCH_MODE` 装配依赖。默认 `mock`，只有 `real` 才校验密钥并创建外部客户端，避免测试和本地启动意外产生费用。

### D2：使用协议隔离外部能力

`SearchService` 保持现有检索接口；新增 `LLMService`，提供关键词、总结、充分性判断和最终摘要四项异步能力。`ResearchEngine` 通过构造函数接收可选 LLM，未注入时继续运行原本确定性逻辑。

### D3：模型输出采用提示词约束 JSON + 解析兜底

不依赖 `response_format`，以兼容 DeepSeek 等 OpenAI 兼容服务。关键词和充分性判断要求 JSON，适配器支持普通 JSON 与 Markdown 代码块，并在解析失败时触发本地回退。

### D4：搜索摘要保存为内部字段

Bocha 的 snippet 存入 `SearchResult` 的私有属性，仅供 LLM 使用，不改变既有 API 的 `title` / `url` 响应契约。

### D5：真实模式仍受原有安全边界约束

研究轮次仍由 `MAX_ROUNDS = 2` 结构性限制；Bocha 请求由超时/重试包装器控制；所有密钥来自环境变量或 `.env`，`.env` 进入 `.gitignore`。

## Verification

- `.venv/bin/pytest -q` 离线全量通过。
- 默认 Mock API 冒烟请求返回 200 和结构化报告。
- 无密钥强制进入 real 模式时，配置校验返回明确缺失变量错误。
- 真实 API 的联网调用需要用户自行填写 `.env` 后手工验证。
