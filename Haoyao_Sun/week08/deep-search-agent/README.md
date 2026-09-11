# 深度研究助手 (Deep Research Agent)

## 📌 项目简介

基于 AI Agent 的深度研究工具，通过 **LLM 智能规划 → 真实 Web 检索 → 语义相关性过滤 → 结构化报告生成** 的闭环，自动生成带真实引用来源的研究报告。

严格遵循 **"零幻觉/绝对真实来源"** 准则，所有内容必须可追溯，禁止任何 Mock 假数据。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# SiliconFlow API
SF_API_KEY=your_siliconflow_api_key_here
SF_API_URL=https://api.siliconflow.cn/v1/chat/completions
SF_MODEL=Pro/MiniMaxAI/MiniMax-M2.5
```

> ⚠️ **注意**：`.env` 包含敏感信息，**请勿提交到版本控制**！

### 3. 启动应用

```bash
streamlit run app.py
```

访问地址：`http://localhost:8501`

---

## 📁 项目结构

```
deep-search-agent/
├── app.py           # Streamlit 主界面：LLM 规划、报告生成、启动校验
├── tools.py         # 搜索工具：DDGS 接入、语义相关性过滤、实体提取
├── .env             # API 配置（敏感信息）
├── requirements.txt # Python 依赖
├── PRD.md           # 产品需求文档
├── CLAUDE.md        # 项目开发规范
└── README.md        # 本文件
```

---

## ⚙️ 技术实现

### 架构图

```
用户输入 ──▶ LLM 智能拆词 ──▶ 多轮检索 ──▶ 相关性过滤 ──▶ 结构化报告
              (plan_subqueries)    (web_search)   (filter_relevance)  (generate_report)
```

### 核心模块

#### 1. app.py（Claude Code 实现）

| 函数 | 功能 |
|------|------|
| `check_api_key()` | 启动时校验 `.env` 配置，未配置则阻止运行 |
| `call_llm()` | 调用 SiliconFlow API 生成双语搜索词 |
| `plan_subqueries_with_llm()` | LLM 动态生成 3-5 个中文+英文学术关键词 |
| `run_research_round()` | 执行单轮检索并记录日志 |
| `generate_report()` | 按实际角度生成结构化中文章节 |
| `main()` | Streamlit 多 Tab 界面 + 状态流转 |

#### 2. tools.py（Claude Code 实现）

| 函数 | 功能 |
|------|------|
| `web_search()` | 接入 `ddgs` 库，无 Key 搜索，超时处理 |
| `filter_relevance()` | 语义相关性过滤，剔除词典/代码仓库/语音模型等无关页面 |
| `extract_key_entities()` | 从主题提取完整实体与关键词 |
| `is_relevant_old()` | 基于实体匹配的相关性校验 |
| `is_english_query()` | 判断是否应使用英文搜索 |

---

## 👥 协同模式

### 项目主导与架构决策（使用者）

- **制定架构**：定义 Agent 闭环流程与"零幻觉"准则
- **缺陷拦截**：
  - 禁止硬编码 API Key
  - 禁止 Mock 假数据/假 URL
  - 禁止死板模板后缀（如"基本情况/发展历史"）
- **需求提出**：
  - 识别检索噪声问题（如搜"RAG"出现"LSAT 词表"）
  - 提出中英双语检索需求
  - 要求启动时校验环境变量

### 代码落地与工程实现（Claude Code）

- **tools.py**：
  - 接入 `duckduckgo-search` (DDGS) 实现无 Key 搜索
  - 编写 `filter_relevance()` 语义过滤函数
  - 实现基于真实 URL 的 `set` 去重机制

- **app.py**：
  - 基于 Streamlit 构建多 Tab 交互界面
  - 实现 `st.status` 动态展示执行轨迹
  - 编写 LLM 双语学术拆词 Prompt（生成英文专有名词）
  - 增加环境变量启动校验与错误拦截

---

## 🔧 技术演进日志

### 迭代 1：密钥安全治理

| 问题 | 解决方案 |
|------|----------|
| 初始代码硬编码明文 `sk-yfq...` Key | 引入 `python-dotenv` 环境变量隔离 |
| 启动时无校验，运行时报错不友好 | 在 `main()` 开头调用 `check_api_key()` + `st.stop()` |

```python
# 修改前
SF_API_KEY = "sk-yfqejlbhabiovwcbjotxdvyjtaamjmifjrqbljjrypkeythx"

# 修改后
from dotenv import load_dotenv
load_dotenv()
SF_API_KEY = os.getenv("SF_API_KEY")
```

### 迭代 2：真实性治理

| 问题 | 解决方案 |
|------|----------|
| 搜索失败时填充 Mock 假数据（如"维基百科 模板链接"） | 彻底删除 `_mock_search()` 函数，搜索失败直接返回 `[]` |
| 参考文献出现重复/无效 URL | 基于真实 URL 进行 `set` 去重 |
| 报告生成可能虚构内容 | 在 Prompt 中明确约束"未找到资料必须说明暂无来源" |

### 迭代 3：检索精准度

| 问题 | 解决方案 |
|------|----------|
| 死板拼接"基本情况/发展历史/重要意义"后缀 | 废除硬编码模板，改用 LLM 动态生成精准搜索词 |
| 搜"RAG"出现"LSAT 词汇表"等无关学术噪声 | 增加 `filter_relevance()` 语义过滤，剔除词典释义、代码仓库、语音模型等 |
| 英文专有名词检索不精准（如"Henry Ford"匹配到"Thierry Henry"） | 提取完整实体进行精确匹配，关键词需多重匹配 |

```python
# 语义过滤规则示例
NOISE_PATTERNS = [
    (r'^github|^pypi|^npmjs', 'code_repo'),      # 代码仓库
    (r'tts|text-to-speech|语音合成', 'tts'),    # 语音模型
    (r'urban dictionary|merriam-webster', 'dictionary'),  # 词典
]
```

---

## 📋 开发规范

### 安全要求

1. **严禁泄漏真实 API Key**：示例配置使用占位符 `your_siliconflow_api_key_here`
2. **环境变量优先**：`load_dotenv()` 必须在文件开头加载
3. **启动校验**：任何调用 LLM 的程序必须先检查 `SF_API_KEY`

### 代码规范

- 类型注解：所有函数需添加类型提示
- 错误处理：外部 API 调用必须 `try/except`
- 日志记录：使用 `st.status` 展示执行轨迹

---

## 📦 依赖

| 库 | 用途 |
|---|---|
| `streamlit` | Web 界面框架 |
| `openai` | LLM API 兼容调用 |
| `requests` | HTTP 请求 |
| `ddgs` | DuckDuckGo 搜索 |
| `python-dotenv` | 环境变量加载 |

---

## 📄 许可证

MIT License