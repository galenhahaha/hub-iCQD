# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 本目录是什么

「综合案例 02 · 深度研究助手」的完整实现（作业 2）。输入一个研究主题，自动完成「规划 → 多轮检索 → 阅读抽取 → 迭代补检 → 综合」，产出一份带来源引用的中文研究报告，并配套内置单页前端与 JSON 持久化。代码已全部落地，并通过真实双 API（DeepSeek + Bocha）端到端联调。

- **产品需求唯一来源**：`README.md`。
- **设计契约**：`实现方案.md`（grill 七问沉淀的决策；字段与架构以其 §3–§4 为准）。
- **启动与验收**：`API.md`（接口表、调用示例、测试与浏览器验收命令）。
- **联调结论**：`联调验收.md`（2026-09-08 真实验收：3 轮检索、11 个检索词、102 个去重来源、high 置信度）。
- **参考实现**（历史排错来源，本目录已可独立运行）：`D:\OneDrive\桌面\八斗AI\项目\Part2-VibeCoding实操\综合案例-02\`。

## 常用命令

须在**项目根**运行，以便解析 `uvicorn` 的模块路径。配置只从进程环境变量读取，不加载 `.env`。

- 建环境：`python -m venv .venv` → 激活 → `pip install -r requirements.txt`
- 启动：PowerShell 执行 `.\start.ps1`，自动使用项目 `.venv`，支持 `-BindAddress`、`-Port`、`-Reload`。也可直接执行 `uvicorn backend.app:app --host 127.0.0.1 --port 8000`。
- 自测（不调 LLM / 网络）：`python -m backend.agent`
- 后端单测：`python -m unittest discover -s tests -v`
- 前端浏览器回归（可选，Playwright，不调外部 API）：`node tests/browser_ui.cjs`
- 真实端到端（会产生 API 费用；带 `research_id` 参数可复用已有任务不另提交）：`node tests/browser_e2e.cjs [research_id]`

## 架构（研究循环，理解本项目的关键）

确定性研究引擎 `DeepResearch`（`backend/engine.py`）编排 4 个**无工具**角色 agent，构成 agentic loop（不是一次性问答）：

```
规划（KeywordAgent 拆 3–5 个关键词）
  → 循环：逐关键词 检索（Bocha web_search）→ 摘要（SummaryAgent，草稿累积）
  → 判断是否补检（JudgeAgent，最多 RESEARCH_MAX_ROUNDS 轮）
  → 综合（置信度规则计算 → ReportAgent 两次调用出元信息 + HTML）
```

- 角色 agent 均无工具、单次 LLM 调用，由 Jinja2 模板驱动（`backend/templates/*.jinja2`，**提示词与代码分离**）。
  - `KeywordAgent` / `JudgeAgent` / `ReportAgent`（第一次）输出 JSON，经 `parse_json` 校验。
  - `SummaryAgent` 是**唯一不解析 JSON** 的角色，输出纯文本正文段（500–900 字，无 URL）。
- `ReportAgent.generate` **两次调用**：先 `report_agent.jinja2` 出 `ReportOutline`（标题/摘要/关键结论/遗留问题），正文分节**由程序把 draft 段落直接映射**（`Section(heading=keyword, body=text)`，不 LLM 重组）；再 `report_html_agent.jinja2` 出完整自包含 HTML。
- 置信度 `_compute_confidence`（`engine.py`）**确定性计算，不调 LLM**：去重来源数 ≥12→high、≥5→medium、否则 low；`info_cutoff` = 最新来源日期（缺省今天）；无来源结论标「模型推断」。
- 编排器 `DeepResearch.run` 纯控制流、不调 LLM；每轮经 `on_progress` 回调把中间结果（process/draft/sources）落盘（`research.py`）。
- 对外接口（`backend/app.py`）：
  - `POST /api/research` → `202` + `{"research_id", "status": "pending"}`，随后 `asyncio.create_task` 后台执行。
  - `GET /api/research/{id}` → `pending/running/completed/failed` 状态 + 四类成果物（report / sources / process+draft / confidence）。
  - `GET /api/research` 历史列表（按创建时间倒序）；`GET /health` 健康检查；`GET /` 内置前端。
- 存储（`backend/storage.py`）：`backend/data/research/{id}.json` 整文件原子写（临时文件 + `os.replace`），`threading.Lock` 保护；`research_id` 校验防止路径穿越。

## 目录结构

```
backend/
├── app.py          # FastAPI 路由 + CORS + lifespan 取消任务 + 托管静态前端
├── config.py       # 读进程环境变量、路径常量、运行参数
├── models.py       # 全部 Pydantic v2 模型（Status 枚举 + 数据契约，字段见实现方案 §4）
├── engine.py       # DeepResearch 编排器 + 确定性置信度
├── research.py     # engine↔storage 接线 + on_progress 落盘 + 状态机
├── storage.py      # JSON 原子持久化
├── tools.py        # Bocha web_search（async httpx，只返回摘要不抓整页）
├── agent/          # base.py + keyword/summary/judge/report + __main__ 自测
├── templates/      # 5 个 Jinja2 提示词模板
├── static/         # index.html（内置单页前端，无 Node 构建）
└── data/research/  # 运行时落盘（.gitignore，不提交）
tests/              # unittest 单测 + Playwright 浏览器回归（可选）
```

## 关键约束与坑（实现必须遵守）

- 模型 DeepSeek `deepseek-v4-flash`，OpenAI 兼容接口 `https://api.deepseek.com/`（`OPENAI_BASE_URL`）。密钥名优先 `DEEPSEEK_API_KEY`，兼容旧名 `OPENAI_API_KEY`。
- **不支持 `Agent(output_type=...)`**（会发 `response_format: json_schema` 被 DeepSeek 拒）。改为提示词强制输出单个 JSON 对象 + `parse_json` 兜底（先 `model_validate_json`，失败再按 ` ```json ` 代码围栏正则抽取，见 `agent/base.py`）。
- DeepSeek 偶发 `200` + 空 `message.content`：`BaseAgent._run` 空输出重试 `LLM_RETRIES` 次、每次 1s 退避。
- 异步只用 `Runner.run`，不用 `run_sync`；在 `agent/base.py` 模块级 `set_default_openai_api("chat_completions")`、`set_tracing_disabled(True)`。
- 密钥通过部署平台注入进程环境变量，不提交、不进代码或文档。`README.md` 的 curl 示例内嵌明文 Bocha key（属泄露），实现只从进程环境变量读，不要在代码/文档复现；SDK 异常信息落盘前会替换其中的密钥（`research.py`）。
- 所有 Pydantic 模型集中在 `models.py`。
- 环境变量运行参数（由 `config.py` 读取）：`DEEPSEEK_API_KEY`、`OPENAI_BASE_URL`、`MODEL_NAME`、`BOCHA_API_KEY`、`BOCHA_SEARCH_COUNT`(10)、`RESEARCH_MAX_ROUNDS`(3)、`LLM_RETRIES`(3)、`FRONTEND_ORIGIN`(http://localhost:3000)。

## 语言约定

界面与生成的报告用中文；代码注释用英文。
