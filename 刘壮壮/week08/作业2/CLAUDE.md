# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

**作业 2：从 0 实现「深度研究助手」（后端 + 前端）。** 本目录目前只有产品规格 `README.md` 和本文件。所有代码在本目录自己设计、自己写。

**不要参考上一层目录。** `../` 是另一份实现，本作业刻意不对照它：不读 `../CLAUDE.md`、不读 `../backend`、不复制、不 import、不软链。以 `README.md` 为准，在本仓库独立完成。

## 产品要求（来自 README.md）

市场/产品同学输入一个研究主题（竞品分析、行业趋势、技术选型、政策解读），工具自动完成检索、阅读、迭代、综合。必须产出四类结果：

1. **结构化研究报告**：摘要、分节正文、关键结论、遗留问题
2. **来源列表**：每条结论能关联到 URL / 标题，可追溯
3. **研究过程记录**：检索了哪些词、读了哪些页面/条目、迭代了几轮
4. **置信度说明**：可靠程度、信息截止时间；没有来源的结论必须标明「模型推断」

核心是 **agentic loop，禁止一次检索就出全文**：

```
规划（把主题拆成可检索的子问题或关键词）
  → 检索
  → 阅读抽取
  → 判断是否够用（不够则补检，再进入下一轮）
  → 综合生成报告
```

迭代、来源可追溯、过程要落盘，这三项是硬要求。第一版阅读抽取用 Bocha 搜索结果里的标题 / 摘要 / snippet 即可，不必先做网页全文抓取。检索轮数必须有上限（默认看 `.env` 的 `RESEARCH_MAX_ROUNDS`）。

## 技术选型（本仓库自定，不要去上层抄）

- 后端：Python + FastAPI；前端：Next.js
- LLM：DeepSeek（OpenAI 兼容，`deepseek-v4-flash`，`https://api.deepseek.com/`），key 来自 `.env`
- 搜索：Bocha `POST https://api.bocha.cn/v1/web-search`（文档见 README）。请求体：`query`（必填）、`summary`、`count`
- 目录、模块怎么拆、提示词怎么管、agent 怎么分，由实现者按上面的 loop 自己设计。先定数据模型和接口，再写循环，再接前端。

若用 DeepSeek：不要依赖 `response_format: json_schema`（会报错）；提示词约束输出 JSON，再自己解析（含代码块兜底）。偶发 HTTP 200 但内容为空，对空输出做有限次重试。

## 接口与前端

研究是慢任务（可能数分钟）：发起后立即返回任务 id，前端轮询直到结束。状态至少：`pending → running → completed / failed`。`running` 期间就要能看到过程（检索词、已读条目、草稿或中间结论），不要等全部完成才有数据。CORS 放行前端源（默认 `http://localhost:3000`）。

建议接口（路径可微调，语义保持即可）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/research` | `{"topic": "..."}` → 202 + 任务 id |
| GET | `/api/research/{id}` | 单条状态与当前产物（轮询） |
| GET | `/api/research` | 历史列表 |
| GET | `/health` | 健康检查 |

前端最低可用：输入主题 → 发起 → 轮询展示过程 → 完成后展示上述四类产物（结论带来源，「模型推断」可见）。不要只丢最终 JSON。

## 密钥与 Git

本目录是独立 git 仓库，按仓库提交作业。

- 本地：`cp .env.example .env` 后填 key；代码用 `python-dotenv` 读 `.env`
- 已有 `.gitignore`、`.env.example`，实现时保留。不要把 key 写进源码 / README / CLAUDE.md，不要 `git add .env`
- **提交**：源码、模板、`requirements.txt`、启动脚本、前端源码、`README.md`、`CLAUDE.md`、`OPTIMIZATION.md`、`.env.example`、`.gitignore`
- **不提交**：`.env`、运行时落盘数据、`__pycache__/`、`.venv/`、`node_modules/`、`.next/`、`.claude/settings.local.json`
- 提交前：`git status` 里不能出现 `.env` 或 `sk-`；`git check-ignore -v .env` 应显示被忽略

## 完成标准

- `cp .env.example .env` 填 key 后，后端与前端能在本目录独立启动
- 一次真实主题能跑通 loop：规划 → 检索 → 抽取 → 判断补检（或明确判定足够）→ 报告；有轮数上限
- 四类产物齐全；结论能点到来源；无来源标「模型推断」；过程已落盘
- 前端走完主流程；`git status` 可交（有源码和 `.env.example`，无密钥和依赖目录）

## 已知限制

第一版只有 Bocha 搜索摘要，时效和来源品质应走置信度，不要在检索里写死「必须今年 / 近一年」。后续待办见 `OPTIMIZATION.md`。

## 目录结构

```
.
├── backend/                 # FastAPI
│   ├── app.py               # 入口：CORS / 日志 / 挂载路由
│   ├── api/                 # HTTP 路由
│   ├── core/                # 配置、LLM 客户端
│   ├── prompts/             # 规划 / 抽取 / 判断 / 综合 提示词
│   ├── models.py            # 任务与产物 schema
│   ├── engine.py            # agentic loop 控制流
│   ├── research.py          # 后台任务 + 落盘
│   ├── search.py            # Bocha 检索
│   └── storage.py           # JSON 落盘
├── frontend/                # Next.js
│   ├── app/                 # 页面
│   ├── components/          # 过程 / 报告 / 来源等 UI
│   └── lib/                 # API 客户端与类型
├── start.sh                 # 启动后端
├── requirements.txt
├── OPTIMIZATION.md          # 后续优化（非规格）
└── .env.example
```

## 常用命令

```bash
cp .env.example .env          # 填入 OPENAI_API_KEY / BOCHA_API_KEY
pip3 install -r requirements.txt
bash start.sh                 # 后端，默认 8000，被占用改端口
npm install && npm run dev    # 前端（仓库根目录 workspace → frontend/），默认 3000
```

冒烟：POST 发起研究，再 GET 轮询，直到 `completed` 或 `failed`。
