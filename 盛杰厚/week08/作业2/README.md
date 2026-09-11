# 深度研究助手（Deep Research Assistant）

> 输入一个研究主题，自动完成 **规划 → 多轮检索 → 阅读抽取 → 补检判断 → 综合成稿**，产出一份**带来源引用、可追溯、含置信度说明**的结构化研究报告。

---

## 1. 背景与定位

市场 / 产品同学经常要围绕一个主题做调研（竞品分析、行业趋势、技术选型、政策解读）。
人工搜索几十个网页、整理资料、写报告，一个主题动辄 2~3 小时，还容易**漏信息**、**来源不可追溯**。

「深度研究助手」的目标是自动化这条链路：给定一个研究主题，自动检索、阅读、迭代、综合，最终输出可交付的研究成果。

## 2. 产品目标（输出物）

一次深度研究，产出四类内容：

| # | 输出物 | 说明 |
|---|--------|------|
| 1 | **结构化研究报告** | 摘要、分节正文、关键结论、遗留问题 |
| 2 | **来源列表** | 每条结论关联 URL / 标题 / 来源，可追溯 |
| 3 | **研究过程记录** | 检索了哪些关键词、读了哪些页面、迭代了几轮 |
| 4 | **置信度说明** | 结论可靠程度、信息截止时间；无来源的结论标注为「模型推断」 |

## 3. 核心流程

区别于一次性问答（一问一答），深度研究是一个**多步迭代**过程：

```
输入主题
   │
   ▼
[1] 规划（Planner）      —— 拆解主题为若干子问题 + 初版检索关键词
   │
   ▼
[2] 多轮检索（Searcher） —— 调用搜索 API，按关键词逐批检索，去重
   │
   ▼
[3] 阅读抽取（Extractor）—— 阅读页面内容，抽取与子问题相关的证据与事实
   │
   ▼
[4] 补检判断（Judge）    —— 评估信息是否充分，决定「继续补检」还是「足够」
   │  └─ 信息不足 ──► 生成新关键词，回到 [2]（记为一轮迭代）
   │
   ▼
[5] 综合成稿（Writer）   —— 汇总证据，生成报告 + 来源列表 + 置信度说明
```

## 4. 技术方案

- **后端语言**：Python
- **Agent 框架**：LangChain（`langchain` + `langgraph`），多 Agent 协作
- **编排方式**：`langgraph` 状态图（`StateGraph`），以共享状态在 Agent 间流转
- **推理引擎**：`config.build_llm()` 统一工厂，通过 `LLM_PROVIDER` 在 **Anthropic / OpenAI 兼容协议**间切换（已实测：本地 Anthropic 网关 + DeepSeek OpenAI 端点）
- **结构化输出**：`config.build_structured_llm()` 统一走 `function_calling`，规避各 provider 差异（见 6.3 节）
- **检索工具**：Bocha Web Search API（见第 5 节）

### 4.1 Agent 划分

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| **Planner** 规划 Agent | 拆解主题为子问题，生成初版检索关键词 | 研究主题 | 子问题列表、关键词列表（`ResearchPlan`） |
| **Searcher** 检索节点 | 调用搜索 API 检索，清洗去重（确定性，无需 LLM） | 关键词 | 原始结果（标题/URL/摘要/时间） |
| **Extractor** 抽取 Agent | 阅读页面，抽取证据与事实 | 页面内容 + 子问题 | 结构化证据（`ExtractResult`） |
| **Judge** 判定 Agent | 判断信息是否充分，决定补检方向 | 已有证据 + 子问题 | 是否补检、新关键词（`Verdict`） |
| **Writer** 综合 Agent | 汇总证据，生成报告与置信度说明 | 全部证据 | markdown 报告 |

> 说明：检索本身是确定性动作，故 `Searcher` 实现为普通函数节点，不做无谓的 LLM 决策；「检索什么」的智能由 Planner / Judge 提供关键词。如需把检索步骤也做成工具调用 Agent，可用 `tools/bocha_search.py` 中的 `web_search_tool`（`@tool` 版本）。

### 4.2 共享状态（State）

在 `langgraph` 中用单一 `State` 对象贯穿全流程，便于记录过程与回溯：

```python
class ResearchState(TypedDict, total=False):
    topic: str                      # 研究主题
    sub_questions: list[str]        # 规划拆解的子问题
    keywords: list[str]             # 当前待检索关键词
    search_history: list[str]       # 已检索过的关键词（用于去重）
    evidence: list[dict]            # 抽取到的证据（含来源）
    pages_read: list[dict]          # 已读页面（研究过程记录）
    iteration: int                  # 当前迭代轮数
    need_more: bool                 # 是否需要补检
    report: str                     # 最终报告（markdown）
    sources: list[dict]             # 来源列表（编号，确定性生成）
    confidence: dict                # 置信度说明
```

### 4.3 目录结构

```
作业2/
├── README.md               # 本文档
├── requirements.txt        # 依赖
├── config.py               # LLM 工厂（Anthropic/OpenAI 切换）+ 全局参数
├── state.py                # ResearchState + Agent 输出 Schema
├── deep_research.py        # 主入口：状态图编排 + 路由 + CLI
├── writers.py              # 来源构建 + report/sources/process 渲染
├── agents/
│   ├── planner.py          # 规划 Agent
│   ├── searcher.py         # 检索节点（封装 Bocha API）
│   ├── extractor.py        # 抽取 Agent
│   ├── judge.py            # 判定 Agent
│   └── writer.py           # 综合 Agent
├── tools/
│   └── bocha_search.py     # 搜索工具封装（纯函数 + @tool）
├── report/                 # 输出目录（报告、来源、过程记录）
└── examples/               # 运行产物存档
    └── 2025-RAG技术选型-deepseek/   # DeepSeek 引擎实测报告
```

## 5. 搜索工具（Bocha Web Search）

文档：<https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK>

**请求**

```bash
curl -X POST "https://api.bocha.cn/v1/web-search" \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query":"天空为什么是蓝色的？","summary":true,"count":10}'
```

**关键参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `query` | string | 检索关键词 |
| `summary` | bool | 是否返回页面摘要（`true` 返回摘要） |
| `count` | int | 返回条数（如 `10`） |

**响应结构（`data.webPages.value[]`）**

| 字段 | 说明 |
|------|------|
| `name` | 结果标题 |
| `url` / `displayUrl` | 链接 |
| `snippet` | 摘要片段 |
| `summary` | 页面摘要（开启 `summary=true` 时） |
| `siteName` | 来源站点 |
| `datePublished` | 发布时间（用于信息截止时间判断） |

## 6. 环境与依赖

```bash
pip install langchain langgraph langchain-anthropic langchain-openai requests
```

依赖（`requirements.txt`）：

```
langchain
langgraph
langchain-anthropic     # Anthropic 兼容协议
langchain-openai        # OpenAI 兼容协议
requests
```

### 6.1 推理引擎配置（`config.py`）

通过环境变量 `LLM_PROVIDER`（或 CLI `--provider`）在两种协议间切换，`config.build_llm()` 统一返回模型：

| Provider | 环境变量 | 默认值 |
|----------|----------|--------|
| `anthropic`（默认） | `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` | `http://127.0.0.1:15721` / `PROXY_KEY` / `claude-haiku-4-5` |
| `openai` | `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | `https://api.deepseek.com` / 内置 key / `deepseek-flash` |

### 6.2 结构化输出与「thinking 模式」陷阱

DeepSeek 的 `deepseek-flash` / `deepseek-v4-pro` 是 **thinking 推理模型**，实测发现：

- `with_structured_output()` 默认走 `json_schema` → 返回 `This response_format type is unavailable now`；
- 强制 `tool_choice="required"` → 返回 `Thinking mode does not support this tool_choice`；
- 但 `tool_choice="auto"`（让模型自主决定调用）→ **thinking 开启时正常返回 tool_calls**。

因此 `config.build_structured_llm()` 采用 **`bind_tools(tool_choice="auto") + PydanticToolsParser`** 方案：thinking 全程开启，不关思考，模型自主决定调用工具，结构化解析由 `PydanticToolsParser` 兜底（未调用工具时抛清晰错误）。

`config.build_llm()` 带 `thinking: bool = True` 参数：

| 调用方 | thinking | 说明 |
|--------|----------|------|
| `build_structured_llm()`（Planner/Extractor/Judge） | 开启 | 用 `tool_choice="auto"`，无需关闭 thinking |
| `build_llm()` 默认（Writer） | 开启 | 纯文本报告生成，保留推理质量 |

如遇新的 OpenAI 兼容端点（官方 OpenAI、vLLM、LM Studio 等非推理模型），可用环境变量 `OPENAI_EXTRA_BODY`（JSON）覆盖透传字段。

### 6.3 CLI 参数

```
--topic          研究主题（必填）
--provider       anthropic | openai（默认取 LLM_PROVIDER，缺省 anthropic）
--model          模型名（覆盖对应 provider 的默认模型）
--max-iterations 最大检索轮数（默认 2）
--out            输出目录（默认 report）
```

## 7. 运行方式

```bash
# 默认：Anthropic 兼容网关（本地 127.0.0.1:15721）
python deep_research.py --topic "2025-2026 生成式 AI 市场规模与竞争格局"

# OpenAI 兼容（DeepSeek，已在 config.py 内置 key/endpoint）
python deep_research.py --topic "2025年RAG与大模型应用的技术选型趋势" --provider openai

# 指定模型 / 最大轮数 / 输出目录
python deep_research.py --topic "主题" --provider openai --model deepseek-v4-pro --max-iterations 3 --out my_report
```

运行后会在输出目录下生成：

- `report.md`       —— 结构化研究报告（摘要 / 分节正文 / 关键结论 / 遗留问题）
- `sources.md`      —— 来源列表（结论 → URL / 标题 / 来源）
- `process.md`      —— 研究过程记录（关键词、已读页面、迭代轮数）

## 8. 报告输出模板

```markdown

# {主题} 研究报告

## 摘要
（3~5 句概括核心结论）

## 1. {子问题一}
正文……（关键事实后标注来源编号 [1]）

## 2. {子问题二}
正文……

## 关键结论
1. 结论一 —— 来源 [1][3]
2. 结论二 —— 来源 [2]（模型推断）

## 遗留问题
- 未覆盖 / 信息不足的点，建议后续补充

## 来源列表
[1] 标题 —— 来源站点 —— URL —— 发布时间
[2] ……

## 置信度说明
- 高置信：结论一（多个独立来源交叉验证）
- 中置信：结论二（单一来源）
- 模型推断：结论三（无来源支撑，由模型根据上下文推断）
- 信息截止时间：2026-09-10
```

## 9. 置信度与「模型推断」标注规则

| 级别 | 判定标准 |
|------|----------|
| **高置信** | 结论由 ≥2 个独立来源交叉验证 |
| **中置信** | 结论仅由单一来源支撑 |
| **低置信** | 来源为二手/转载，或信息陈旧 |
| **模型推断** | 无任何来源支撑，由模型推理得出，须显式标注 |

每条结论的置信度取决于**来源数量、来源可信度、信息时效性**三个维度。

## 10. 研究过程记录（示例）

```markdown
## 研究主题
2025-2026 生成式 AI 市场规模与竞争格局

## 规划（Planner）
子问题：
1. 市场规模与增速
2. 主要玩家与竞争格局
3. 区域分布（北美/亚太/欧洲）

## 检索记录
- 第 1 轮：关键词 ["生成式AI 市场规模 2025", "生成式AI 竞争格局", ...]
- 第 2 轮（补检）：关键词 ["生成式AI 中国 市场", ...]

## 已读页面
- [1] 标题 —— URL（发布时间）
- [2] ...

## 迭代轮数
共 2 轮检索，阅读 15 个页面，抽取 23 条证据。
```
