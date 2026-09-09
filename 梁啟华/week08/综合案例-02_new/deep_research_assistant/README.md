# 深度研究助手 · Deep Research Assistant

> 输入一个研究主题，自动完成 **多轮检索 → 阅读抽取 → 智能补检 → 综合生成**，
> 产出一份 **带来源引用、可追溯、含置信度说明** 的结构化研究报告。
> 本实现以 **FastAPI 封装为 Web 服务**，采用 **异步任务 + 结果轮询** 的模式。

对应需求文档：`../README.md`（综合案例 02 · 深度研究助手）。

---

## 目录

1. [功能特性](#功能特性)
2. [项目结构](#项目结构)
3. [核心业务流程](#核心业务流程)
4. [快速开始](#快速开始)
5. [配置文件说明](#配置文件说明)
6. [接口说明](#接口说明)
7. [轮询调用示例](#轮询调用示例)
8. [命令行示例客户端](#命令行示例客户端)
9. [离线模式（不配置 LLM）](#离线模式不配置-llm)
10. [生产化改造方向](#生产化改造方向)

---

## 功能特性

- ✅ **异步任务 + 结果轮询**：提交后立即返回 `task_id`，研究与 HTTP 响应解耦；
  轮询接口可实时看到「规划 / 检索 / 阅读 / 补检 / 综合」各阶段进度。
- ✅ **多轮检索闭环**：先拆解子问题 → 逐关键词检索 → 真实抓取网页正文“阅读” →
  LLM 判断是否有信息缺口 → 必要时补检 → 综合生成。
- ✅ **四类成果齐备**：
  1. 结构化研究报告（标题 / 摘要 / 分节正文 / 关键结论 / 遗留问题）
  2. 来源列表（编号 ↔ URL / 标题 / 站点 / 时间，可追溯）
  3. 研究过程记录（关键词、阅读页数、迭代轮数）
  4. 置信度说明（可靠性 / 信息截止 / 无来源结论标注为“模型推断”）
- ✅ **Markdown 一键导出**：`/markdown` 接口直接拿可保存的 `.md` 文本。
- ✅ **离线兜底**：没配 LLM Key 也能跑通链路（见[离线模式](#离线模式不配置-llm)）。
- ✅ **厂商无关**：LLM 走 OpenAI Chat Completions 兼容协议，DeepSeek / OpenAI / 通义 / 豆包均可接入。
- ✅ 全量代码**中文注解**，方便学习与二次开发。

---

## 项目结构

```
deep_research_assistant/
├── README.md               # 本使用说明
├── requirements.txt        # 依赖清单
├── .env.example            # 环境变量模板（复制为 .env 使用）
├── run.py                  # 本地启动入口
├── examples/
│   └── demo_client.py      # 命令行示例客户端（提交 + 轮询 + 保存报告）
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI 入口：路由 + 生命周期组装
    ├── config.py           # 配置中心（读环境变量 / .env）
    ├── schemas.py          # Pydantic 请求/响应模型
    ├── llm.py              # LLM 客户端（OpenAI 兼容，含 JSON 容错解析）
    ├── search.py           # Bocha 网页搜索客户端
    ├── reader.py           # 网页正文抓取与净化
    ├── engine.py           # ⭐ 深度研究引擎（核心业务流程）
    └── task_manager.py     # 异步任务管理器（提交 + 轮询 + 清理）
```

---

## 核心业务流程

引擎编排逻辑见 `app/engine.py::ResearchEngine.run`，对应需求文档中的“核心流程”：

```
输入主题
   │
   ▼
[1] 规划        —— LLM 把主题拆成 3~6 个子问题，每个子问题给检索关键词
   │
   ▼
[2] 检索        循环 r 轮：对每个关键词调 Bocha 网页搜索，结果进“证据池”
   │
   ▼
[3] 阅读抽取    —— 并发抓取若干网页正文（并发上限 4），失败自动用摘要降级
   │
   ▼
[4] 判断补检    —— LLM 看材料是否够回答子问题；有缺口则给“补检关键词”，回到 [2]
   │             （离线模式跳过判断；最多 = 1 轮初始 + MAX_ROUNDS 轮补检）
   ▼
[5] 综合生成    —— LLM 依据带编号的来源材料写结构化 JSON 报告（含引用与置信度）
   │
   ▼
输出：结构化报告 + 来源列表 + 过程记录 + 置信度说明 + Markdown 文本
```

技术要点：
- **异步**：引擎整体是 `async` 协程，跑在 `asyncio` 后台任务里；网页抓取用
  `asyncio.gather` 并发，不阻塞事件循环。
- **异步任务模式**：`task_manager.py` 的 `submit()` 用
  `asyncio.get_running_loop().create_task(...)` 启动后台执行，并维护任务状态机
  `pending → running → done / failed`。
- **轮询**：`GET /research/{task_id}` 每次返回最新的 `phases` 与最终 `result`。

---

## 快速开始

### 0) 环境要求

- Python 3.10+（用了 `X | None` 类型语法）
- 能访问 Bocha 网页搜索 API（README 已给出示例 Key）
- （可选）一个 LLM 的 API Key，用于“完整模式”的高质量研究

### 1) 安装依赖

```bash
cd deep_research_assistant
pip install -r requirements.txt
```

### 2) 配置

```bash
# 复制模板并编辑（也可直接用环境变量，不建 .env 也能跑）
cp .env.example .env
```

编辑 `.env`，最关键的是 `LLM_API_KEY`（完整模式需要）；`BOCHA_API_KEY`
默认已填课程文档的示例 Key。

### 3) 启动服务

```bash
python run.py
# 或：uvicorn app.main:app --host 127.0.0.1 --port 8000
```

看到如下输出即成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

- 交互式接口文档（Swagger）：http://127.0.0.1:8000/docs
- 服务信息/健康检查：http://127.0.0.1:8000/ 和 http://127.0.0.1:8000/health

---

## 配置文件说明

复制 `.env.example` 为 `.env` 后按需修改，所有项均有合理默认值：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 服务监听地址 |
| `BOCHA_API_KEY` | 课程示例 Key | 建议替换为自己申请 / 文档中的 Key |
| `LLM_API_KEY` | 空 | **完整模式必填**；留空则为离线模式 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 任意 OpenAI 兼容网关地址 |
| `LLM_MODEL` | `deepseek-chat` | 使用的模型名 |
| `MAX_ROUNDS` | `1` | 初始检索之外最多补检几轮（0~3） |
| `RESULTS_PER_QUERY` | `5` | 每个关键词取几条搜索结果 |
| `MAX_PAGES_TO_READ` | `8` | 最多真实抓取阅读几个网页正文 |
| `MAX_SOURCES_TOTAL` | `25` | 最终报告保留来源上限 |
| `TASK_TTL_SECONDS` | `3600` | 已完成任务的内存保留时长 |

---

## 接口说明

### ① 提交研究任务（异步）

```
POST /api/v1/research
Content-Type: application/json
```

请求体：

```json
{
  "topic": "2026 年国产大模型市场格局与头部厂商对比",
  "max_rounds": 1,
  "results_per_query": 5,
  "extra_instructions": "重点覆盖：各家营收、开源策略、落地场景"
}
```

- `topic`：必填，2~200 字符；
- 其余可选，不传时使用服务端配置。

响应（HTTP 202）：

```json
{
  "task_id": "ab12cd34ef56",
  "status": "pending",
  "research_mode": "full",
  "topic": "2026 年国产大模型市场格局与头部厂商对比",
  "poll_url": "/api/v1/research/ab12cd34ef56",
  "notice": null
}
```

拿到 `task_id` 后即可轮询。

### ② 轮询任务状态 / 结果

```
GET /api/v1/research/{task_id}
```

响应示例：

```json
{
  "task_id": "ab12cd34ef56",
  "status": "done",
  "created_at": "2026-09-09T10:00:00+08:00",
  "updated_at": "2026-09-09T10:00:35+08:00",
  "research_mode": "full",
  "phases": [
    { "phase": "规划", "message": "开始拆解研究主题：...", "timestamp": "...", "round": null },
    { "phase": "检索", "message": "第 1/2 轮检索开始，共 6 个关键词", "timestamp": "...", "round": 1 }
  ],
  "error": null,
  "result": {
    "research_mode": "full",
    "topic": "...",
    "title": "...",
    "abstract": "...",
    "sections": [
      { "heading": "市场格局", "content": "...（正文可引用 [1][2]）", "source_ids": [1, 2] }
    ],
    "key_conclusions": [
      { "conclusion": "...", "confidence": "medium", "source_ids": [1], "source_urls": ["https://..."] }
    ],
    "open_questions": ["..."],
    "confidence_notes": {
      "overall": "总体可靠性说明",
      "info_cutoff": "信息大致截止到 2026-08",
      "inference_policy": "正文中未用 [编号] 引用的内容一律视为模型推断"
    },
    "sources": [
      { "id": 1, "title": "...", "url": "https://...", "site_name": "...", "date": "...",
        "snippet": "...", "query": "...", "round": 1, "question": "..." }
    ],
    "process_log": [ { "phase": "规划", "message": "...", "timestamp": "...", "round": null } ],
    "stats": { "rounds_used": 2, "queries_run": 8, "pages_read": 6,
               "llm_calls": 3 },
    "generated_at": "...",
    "markdown": "# ...\n\n 完整可读报告 ..."
  }
}
```

`status` 取值：`pending` / `running` / `done` / `failed`。
- `running`：重点看 `phases`，前端可渲染成实时进度；
- `done`：`result` 可用，其中 `markdown` 为可直接展示/保存的报告文本；
- `failed`：看 `error` 字段原因。

### ③ 导出 Markdown 报告

```
GET /api/v1/research/{task_id}/markdown
```

- 任务进行中返回 `409`；成功返回：

```json
{
  "task_id": "ab12cd34ef56",
  "markdown": "# ...",
  "filename": "deep_research_ab12cd34ef56.md"
}
```

---

## 轮询调用示例

**方式一：命令行客户端（推荐，已封装好轮询逻辑）**

```bash
python examples/demo_client.py \
  --topic "2026 年国产大模型市场格局与头部厂商对比" \
  --out report.md
```

会打印实时阶段进度，结束后把完整 Markdown 报告存到 `report.md`。

**方式二：curl 手动两步走**

```bash
# 1) 提交任务
curl -X POST "http://127.0.0.1:8000/api/v1/research" \
  -H "Content-Type: application/json" \
  -d '{"topic":"为什么天空是蓝色的？","extra_instructions":"用通俗的语言解释"}'
# -> 拿到 task_id

# 2) 循环轮询（把 <task_id> 替换成上一步返回的 id）
curl "http://127.0.0.1:8000/api/v1/research/<task_id>"
```

**方式三：Python httpx 极简轮询片段**

```python
import time, httpx

client = httpx.Client(base_url="http://127.0.0.1:8000")
r = client.post("/api/v1/research", json={"topic": "你的主题"}).json()
task_id = r["task_id"]

while True:
    state = client.get(f"/api/v1/research/{task_id}").json()
    if state["status"] in ("done", "failed"):
        break
    for p in state.get("phases", [])[seen:]:  # seen 记录已打印的条数
        print(p["phase"], p["message"])
    time.sleep(2)

print(state["result"]["markdown"])   # 最终报告
```

---

## 命令行示例客户端

```
python examples/demo_client.py --help
```

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--base-url` | 服务地址 | `http://127.0.0.1:8000` |
| `--topic` | 研究主题 | 示例主题 |
| `--extra` | 补充要求 | 空 |
| `--max-rounds` | 覆盖补检轮数 | 用服务端默认 |
| `--poll-interval` | 轮询间隔（秒） | 2 |
| `--timeout` | 最长等待（秒） | 600 |
| `--out` | 保存 Markdown 报告的路径 | 不保存 |

---

## 离线模式（不配置 LLM）

当未设置 `LLM_API_KEY` 时，服务自动进入 `offline` 模式（根接口与提交响应里
都有 `research_mode` 提示）：

- **仍然可用**：规划降级为主题自身、检索、网页正文阅读、来源收集、Markdown 报告生成照常；
- **不做什么**：不做语义综合与智能补检（避免编造内容），报告为检索结果的机械拼接；
- **如何识别**：报告 `confidence_notes` 会明确标注「离线模式 / 低置信度 / 视为模型推断」，
  `key_conclusions` 为空。

离线模式适合先验证链路与检索覆盖率；要拿到真正可用的深度研究报告，请配置 LLM：

```bash
# .env
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1   # 换成你用的兼容网关
LLM_MODEL=deepseek-chat
```

---

## 生产化改造方向

当前实现刻意保持“单进程 + 内存”的最小复杂度，便于讲解异步任务模式。上生产前建议：

1. **任务存储**：把 `task_manager` 的内存 dict 换成 Redis（如 `TaskEntry` 存 JSON），
   支持多进程/多实例与重启恢复；
2. **任务队列**：用 Celery / ARQ / RQ 把“进行中”的研究任务交给后台 Worker，
   避免占用 Web 进程事件循环；
3. **限流与配额**：为搜索与 LLM 调用加并发信号量与按任务的 token/时长预算；
4. **缓存与去重**：对相同主题的结果做缓存；网页正文抓取可加域名级背压；
5. **鉴权**：为写接口加 API-Key 校验，避免任意调用消耗额度。

---

## License / 说明

本项目为《Week08 · Part2 VibeCoding 实操 · 综合案例 02》教学演示代码，
代码均含中文注解，可按需学习、修改与二次开发。
