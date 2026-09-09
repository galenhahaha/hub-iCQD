## 1. 配置与依赖

- [x] 1.1 增加 `openai` 与 `python-dotenv` 依赖。
- [x] 1.2 新增 `app/config.py` 和 `.env.example`，实现模式、端点、模型、超时、重试及密钥配置校验。
- [x] 1.3 更新 `.gitignore` 和项目协作说明，禁止提交或打印密钥。

## 2. 真实适配器

- [x] 2.1 实现 `BochaSearchService`，将真实网页搜索响应转换为 `SearchResult`。
- [x] 2.2 实现 `OpenAICompatibleLLMService`，支持关键词、总结、充分性判断和摘要生成。
- [x] 2.3 加入 JSON 解析、空输出和外部调用异常处理。

## 3. 编排与装配

- [x] 3.1 让 `ResearchEngine` 接收可选 `LLMService`，真实模式调用模型，失败时回退确定性逻辑。
- [x] 3.2 更新 FastAPI 依赖装配，根据 `RESEARCH_MODE` 选择 Mock 或真实服务。
- [x] 3.3 保持 API 响应、轮次上限、来源去重和离线 Mock 行为不变。

## 4. 文档与验证

- [x] 4.1 更新 README、CLAUDE.md 和架构文档，说明真实模式配置和教学级限制。
- [x] 4.2 安装依赖并运行 `.venv/bin/pytest -q`。
- [x] 4.3 运行默认 Mock 模式 API 冒烟测试。
- [x] 4.4 验证无密钥进入 real 模式时给出清晰配置错误。
