# API 启动与验收

在项目根目录运行（PowerShell）：

```powershell
.\start.ps1
```

脚本自动使用项目 `.venv` 并切换到项目根目录，无需提前激活虚拟环境。可通过 `-BindAddress 127.0.0.1 -Port 8001` 修改监听地址和端口；开发时可加 `-Reload` 启用自动重载。按 `Ctrl+C` 停止服务。脚本继承当前进程环境变量，不加载 `.env`。

打开 `http://127.0.0.1:8000/` 使用「知序 · 深度研究助手」前端，或打开 `http://127.0.0.1:8000/docs` 交互调用接口。前端为内置单页 HTML，无 Node 构建步骤，使用同源 API。启动会自动创建 `backend/data/research/`。CORS 允许环境变量中的 `FRONTEND_ORIGIN`，默认 `http://localhost:3000`，支持 GET、POST 和 JSON 请求预检。

配置只读取服务进程的环境变量，不自动加载 `.env` 文件。部署时通过服务管理器、容器或部署平台注入 `DEEPSEEK_API_KEY`、`BOCHA_API_KEY`。DeepSeek 同时兼容旧名称 `OPENAI_API_KEY`，两者都有值时优先使用 `DEEPSEEK_API_KEY`。修改配置后重启服务，密钥不会发送到浏览器。`.env.example` 仅作为变量清单参考。

本地 PowerShell 示例（占位值需替换；变量仅作用于当前终端及其启动的子进程）：

```powershell
$env:DEEPSEEK_API_KEY = '你的模型密钥'
$env:BOCHA_API_KEY = '你的搜索密钥'
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

生产环境应在实际启动服务的配置中注入变量；另一个终端设置的变量不会自动传给已运行的服务。不要为 Uvicorn 指定 `--env-file`。

前端支持主题示例、历史任务切换、每 2 秒自动轮询、阶段性草稿展示、失败说明与断线重试。四个标签页分别展示报告、来源、研究过程和置信度；URL 中保存研究 ID，刷新后恢复选中任务。完成后可导出 Markdown 报告、查看隔离的 HTML 排版预览。移动端通过左上角菜单打开历史研究。

| 接口 | 响应 |
| --- | --- |
| `GET /` | `200`，内置前端 `backend/static/index.html` |
| `GET /health` | `200`，`{"status":"ok"}` |
| `POST /api/research` | 请求 `{"topic":"研究主题"}`；响应 `202`，`{"research_id":"UUID","status":"pending"}` |
| `GET /api/research/{research_id}` | `200`，完整研究记录；不存在或非法 ID 返回 `404` |
| `GET /api/research` | `200`，按创建时间倒序的研究记录数组 |

主题会去除首尾空白，长度必须为 1–500 字符，否则返回 `422`。POST 会先保存 pending 记录，再调度后台任务；返回的 pending 是受理状态，轮询时任务可能已进入 running 或终态。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
$payload = @{ topic = '大模型 RAG 技术选型' } | ConvertTo-Json
$accepted = Invoke-RestMethod http://127.0.0.1:8000/api/research -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
Invoke-RestMethod "http://127.0.0.1:8000/api/research/$($accepted.research_id)"
Get-Content -Encoding UTF8 "backend/data/research/$($accepted.research_id).json"
```

记录状态为 `pending → running → completed/failed`。每次进度回调写入 `process`、`draft`、`sources` 并刷新 `updated_at`；完成时写入全部报告成果物。失败时保留最近一次成功落盘的进度，并记录 `error`。正常关闭服务会取消本进程内未完成任务并标记 failed。任务由当前进程管理，强制终止或断电后不会自动恢复历史 pending/running 任务。

JSON 顶层字段固定为：

```text
research_id, topic, status, created_at, updated_at, error,
report, report_html, sources, draft, process, confidence
```

`created_at`、`updated_at` 使用 UTC ISO 8601 时间。初始 `report/process/confidence` 为 null，`report_html` 为空字符串，`sources/draft` 为空数组。完成后 `report` 包含摘要、分节、关键结论与遗留问题，`process` 包含规划、检索词、来源 URL、轮数与步骤。

自动验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m backend.agent
```

测试使用临时目录。接线测试通过模拟角色输出及搜索结果验证真实引擎的成功与失败落盘；HTTP 冒烟测试启动真实 uvicorn 子进程，验证 health、202 + UUID、轮询结果与磁盘 JSON 一致，结束后关闭子进程。该 HTTP 测试显式清空两种 DeepSeek 密钥名称及 Bocha 密钥，验证缺少配置时返回 failed，不调用外部服务。

浏览器验收脚本使用 Playwright，属于可选开发工具；本次验收使用 Playwright 1.62.1。可另外安装 Node 包和 Chromium，或用 `BROWSER_EXECUTABLE_PATH` 指定现有 Chrome：

```powershell
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
```

先启动服务，再运行不调用外部 API 的前端回归测试。该脚本拦截研究接口，核对空白校验、阶段草稿、失败保留进度、历史切换时过期响应处理、断线重试、HTML 隔离、键盘标签切换和 360px 布局：

```powershell
node tests/browser_ui.cjs
```

配置双 key 后，显式运行真实验收：

```powershell
node tests/browser_e2e.cjs
# Reuse an existing completed task without submitting another paid request.
node tests/browser_e2e.cjs <research_id>
```

不提供 ID 时脚本会通过前端提交真实话题，产生外部 API 调用费用。脚本轮询到 completed 后核对全部成果、引用关联、磁盘 JSON、四个标签页、HTML 预览、Markdown 下载、刷新恢复及手机布局。截图、下载报告和 `acceptance.json` 保存在 `backend/data/verification/`（不提交 Git）。
