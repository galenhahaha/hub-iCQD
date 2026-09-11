# CLAUDE.md - 项目规范与开发指南
# PostToolUse Hook 测试

## 1. 项目概述

**项目名称**：深度研究助手 (Deep Research Agent)

**技术栈**：Python + Streamlit + SiliconFlow LLM + DuckDuckGo 搜索 + dotenv

---

## 2. 目录结构

```
deep-search-agent/
│
├── app.py                    # Streamlit Web 主界面
├── tools.py                  # 搜索工具 + 相关性过滤
├── CLAUDE.md                 # 本文件：项目规范
├── PRD.md                    # 产品需求文档
├── .env                      # API 配置（敏感信息，不提交）
└── requirements.txt          # Python 依赖
```

---

## 3. 依赖库

| 库名 | 版本 | 用途 |
|------|------|------|
| `streamlit` | ≥1.28.0 | Web 界面框架 |
| `openai` | ≥1.3.0 | LLM API 调用（SiliconFlow 兼容） |
| `requests` | ≥2.31.0 | HTTP 请求 |
| `ddgs` | ≥3.0.0 | DuckDuckGo 搜索 |
| `python-dotenv` | ≥1.0.0 | 环境变量加载 |

**安装命令**：

```bash
pip install -r requirements.txt
```

---

## 4. 运行命令

```bash
streamlit run app.py
```

默认访问地址：`http://localhost:8501`

---

## 5. 环境变量配置

**重要**：`.env` 文件包含敏感 API Key，**严禁提交或打包**！

在项目根目录创建 `.env` 文件：

```bash
# SiliconFlow API Key
SF_API_KEY=your_api_key_here
```

---

## 6. 编码规范

### 6.1 命名规范

- **文件命名**：小写字母 + 下划线 (`snake_case`)
- **类命名**：大驼峰 (`PascalCase`)
- **函数/变量命名**：小写下划线 (`snake_case`)
- **常量**：全大写 + 下划线 (`UPPER_SNAKE_CASE`)

### 6.2 类型注解

所有函数必须添加类型注解。

### 6.3 文档字符串

使用 Google 风格的文档字符串。

### 6.4 错误处理

- 所有外部 API 调用必须捕获异常
- 使用 `try/except` 包裹网络请求
- 记录错误日志并返回友好的用户提示

### 6.5 Streamlit 最佳实践

- 使用 `st.session_state` 管理状态
- 避免全局可变变量
- 使用 `st.status` 展示执行轨迹

### 6.6 安全规范

- 严禁在代码中硬编码 API Key
- 必须使用 `load_dotenv()` + `os.getenv()` 读取敏感配置
- 启动时检查 API Key 是否配置，未配置则阻止运行

---

## 7. 核心模块说明

### 7.1 app.py

- 主界面：输入研究主题、设置轮次
- LLM 智能规划子问题（中英双语学术关键词）
- 研究执行与报告生成
- 启动校验：检查 SF_API_KEY

### 7.2 tools.py

- `web_search()`: 搜索 + 语义相关性过滤
- `filter_relevance()`: 噪声剔除（词典、代码仓库、语音模型等无关页面）
- `extract_key_entities()`: 实体提取

---

## 8. 开发流程

1. **规划阶段**：先设计模块接口
2. **编码阶段**：按模块逐一实现
3. **集成阶段**：组合各模块，调试端到端流程
4. **优化阶段**：完善 UI，提升质量

---

## 9. 参考资料

- [Streamlit 文档](https://docs.streamlit.io/)
- [SiliconFlow API](https://siliconflow.cn)
- [DuckDuckGo](https://duckduckgo.com)