# Evidence-first Travel Intelligence Agent — Runbook

本文档说明如何在本项目中安装、配置并运行 **东亚旅游景点情报 Agent**（FastAPI + Evidence-first 状态机），以及如何运行评测与上传 GitHub。

---

## 1. 概述

| 项目 | 说明 |
|------|------|
| 服务入口 | `backend/app/main.py`（FastAPI） |
| 状态机 | `backend/app/orchestrator/state_machine.py` |
| 首期支持区域 | 日本、中国、韩国 |
| 核心能力 | 单景点情报 / 多景点比较 / 轻量行程建议 |
| 数据模式 | MVP 阶段以 mock tools 为主，接口按真实 API 设计 |

设计原则：**工具返回 Evidence → Agent 基于 Evidence 总结 → Composer 生成回答**。禁止 LLM 直接编造开放时间、票价、路线。

---

## 2. 环境要求

- **Python** 3.10+（已在 3.13 验证）
- **操作系统**：Windows / macOS / Linux
- **Git**（上传 GitHub 时需要）
- **可选**：`ANTHROPIC_API_KEY`（无 key 时 `LLM_MODE=mock` 可离线演示）

---

## 3. 安装

在项目根目录执行：

```bash
cd "E:\学习文件\研究生\就业\Agent学习\Evidence-first Travel Intelligence Agent\backend"

pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
```

---

## 4. 配置

编辑 `backend/.env`：

```env
LLM_MODE=mock
LOG_LEVEL=INFO
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_MODE` | 否 | `mock`（默认离线）/ `auto` / `anthropic` |
| `ANTHROPIC_API_KEY` | 使用真实 LLM 时 | Anthropic API 密钥 |
| `ANTHROPIC_MODEL` | 否 | Claude 模型名 |
| `LOG_LEVEL` | 否 | `INFO` / `DEBUG` |

**安全提示**：不要将 `backend/.env` 提交到 Git（已在 `.gitignore` 中忽略）。

### 验证配置

```bash
cd backend
python -c "from app.config import get_settings; s=get_settings(); print('llm_mode:', s.llm_mode)"
```

---

## 5. 启动服务

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/travel/supported-regions
```

API 文档：浏览器打开 `http://127.0.0.1:8000/`（用户界面）或 `http://127.0.0.1:8000/admin`（Swagger API 后台）

---

## 6. API 使用示例

### 6.1 单景点情报

```bash
curl -X POST http://127.0.0.1:8000/api/travel/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"京都清水寺适合带父母去吗？\",\"user_context\":{\"party\":[\"elderly\"],\"pace\":\"relaxed\"}}"
```

### 6.2 多景点比较

```bash
curl -X POST http://127.0.0.1:8000/api/travel/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"清水寺、伏见稻荷、岚山竹林哪个更适合老人？\"}"
```

### 6.3 轻量行程

```bash
curl -X POST http://127.0.0.1:8000/api/travel/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"我住在明洞，想安排一天首尔文化游。\"}"
```

### 6.4 响应字段

| 字段 | 说明 |
|------|------|
| `answer` | 结构化自然语言回答 |
| `structured_result` | 推荐 / 比较表 / 行程等结构化结果 |
| `visible_trace` | 用户可理解的执行轨迹 |
| `evidence_summary` | 证据来源摘要 |
| `conflicts` | 来源冲突记录 |
| `limitations` | 限制与假设说明 |
| `field_evidence_summary` | 字段级证据摘要 |
| `citation_check_result` | 引用校验结果 |
| `tool_traces` | 工具调用轨迹 |

---

## 7. 运行评测

```bash
cd backend
pytest -q
```

Golden queries 位于 `backend/app/evals/golden_queries.json`，覆盖：

- 单景点（清水寺 / 故宫 / 景福宫）
- 多景点比较（京都三景点）
- 行程建议（明洞出发首尔文化游）

---

## 8. 目录结构

```text
Evidence-first Travel Intelligence Agent/
├── RUNBOOK.md                 # 本文档
├── README.md                  # 项目简介
├── upload_to_github.ps1       # Windows 一键上传
├── upload_to_github.sh        # macOS/Linux 一键上传
├── setup_project_credentials.ps1
├── set_project_pat.ps1
├── fix_github_auth.ps1
└── backend/
    ├── app/
    │   ├── main.py
    │   ├── orchestrator/state_machine.py
    │   ├── agents/
    │   ├── tools/mock_data.py
    │   ├── schemas/
    │   └── evals/
    ├── requirements.txt
    └── .env.example
```

---

## 9. 状态链（QueryUnderstanding-first）

`TravelAgentStateMachine` 主流程（`backend/app/orchestrator/state_machine.py`）：

```text
User Query
  → QueryUnderstandingPromptState     # 会话上下文 + 转写 + TravelTask + ClarificationGate
  → RegionGate                        # 优先 TravelTask.country/city
  → TravelTaskToUserGoalAdapter       # 主路径 UserGoal（IntentAgent 仅 fallback）
  → InformationNeedPlanner + ToolRouter
  → Tools → Evidence
  → EvidenceAggregator → ReviewMining → Scorer → Composer → CitationChecker
```

澄清路径（`needs_clarification=true`）在 QueryUnderstanding 后直接返回，不调用 RegionGate / IntentAgent / Tools。

旧版入口 `Region Gate → Intent → ...` 已废弃；`IntentAgent` 仅在 TravelTask 不可用时作为 fallback。

---

## 10. 扩展真实数据源

1. 在 `backend/app/tools/` 新增 tool，实现 `BaseTool.run()` 并返回 `Evidence`
2. 在 `backend/app/tools/__init__.py` 的 `ToolRegistry` 中替换 mock
3. 在 `backend/app/config.py` 增加对应 API key 配置
4. 在 `backend/app/evals/` 补充验收用例

**原则**：开放时间 / 票价 / 预约政策优先 `official` 证据；天气用 `weather_api`；交通用 `transit_api` / `map`。

---

## 11. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `ModuleNotFoundError: app` | 未在 `backend/` 目录启动 | `cd backend` 后再运行 uvicorn / pytest |
| 端口占用 | 8000 已被占用 | 换端口 `--port 8001` |
| 回答过于模板化 | `LLM_MODE=mock` | 配置 `ANTHROPIC_API_KEY` 并设 `LLM_MODE=anthropic` |
| 景点未识别 | mock 库无该景点 | 在 `mock_data.py` 的 `PLACE_REGISTRY` 添加 |
| pytest 无测试 | 未配置 `pytest.ini` | 确认 `backend/pytest.ini` 存在，在 `backend/` 运行 |
| 非日韩中查询被拒 | Region Gate 设计 | 预期行为；扩展国家需改 `config.py` 与 Region Gate |

---

## 12. 上传项目到 GitHub

默认远程仓库：

**https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git**

分支：`main`。推送前请确认你有该仓库的 **write** 权限（或先用 `-RemoteUrl` 指向你自己的仓库）。

> 若 GitHub 上尚未创建该仓库，请先在 GitHub 网页 **New repository** 创建同名空仓库，再执行上传脚本。

### 12.1 不会上传的内容

`.gitignore` 已排除：

| 路径/模式 | 说明 |
|-----------|------|
| `backend/.env` / `.env` | API 密钥 |
| `__pycache__/`、`.pytest_cache/` | 缓存 |
| `*.pat`、`github-pat.txt`、`*.gitcredentials` | 令牌或凭据文件 |
| `node_modules/`、`.next/` | 前端构建产物（预留） |

### 12.2 一键上传（推荐）

**Windows（PowerShell）**，在项目根目录：

```powershell
# 默认提交信息并 push
.\upload_to_github.ps1

# 自定义提交说明
.\upload_to_github.ps1 -Message "feat: travel agent MVP with runbook"

# 仅预览将执行的 git 命令
.\upload_to_github.ps1 -DryRun
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-RemoteUrl` | `https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git` | 远程地址 |
| `-Branch` | `main` | 分支名 |
| `-Message` | `init: Evidence-first Travel Intelligence Agent MVP` | 提交说明 |
| `-DryRun` | — | 只打印命令，不执行 commit/push |

**macOS / Linux**：

```bash
bash upload_to_github.sh
bash upload_to_github.sh "feat: update runbook"
DRY_RUN=1 bash upload_to_github.sh
```

### 12.3 首次配置 GitHub 凭据（HTTPS + PAT）

1. 打开 [GitHub Tokens](https://github.com/settings/tokens)
2. **Generate new token (classic)**，勾选 **`repo`**
3. 复制 Token（`ghp_...` 或 `github_pat_...`）

**方式 A：仅本仓库独立凭据（推荐）**

```powershell
.\setup_project_credentials.ps1
git push -u origin main
# 用户名: Laniccc | 密码: 粘贴 PAT
```

**方式 B：PAT 只保存在 `.git/credentials`**

```powershell
.\setup_project_credentials.ps1 -UseLocalFile
# 或交互式：
.\set_project_pat.ps1
git push -u origin main
```

**清除本仓库错误凭据：**

```powershell
.\fix_github_auth.ps1
```

### 12.4 推送失败：403 / 认证错误

| 现象 | 处理 |
|------|------|
| `403` / `Permission denied` | 运行 `.\fix_github_auth.ps1`，用新 PAT 重试 |
| 用了网站登录密码 | 必须使用 PAT |
| 仓库不存在 | 先在 GitHub 创建空仓库 |
| 更换远程 | `.\upload_to_github.ps1 -RemoteUrl "https://github.com/<user>/<repo>.git"` |

---

## 13. 运维与安全建议

1. **密钥**：仅存放在 `backend/.env`，不要写入代码或提交 Git。
2. **评论数据合规**：mock 阶段只存摘要；接真实 API 时遵守平台条款。
3. **反爬**：不得绕过登录、验证码或批量抓取受保护内容。
4. **证据优先**：缺少关键证据时必须标注不确定，不得给确定性结论。

---

## 14. 快速检查清单

- [ ] Python 3.10+ 已安装
- [ ] `cd backend && pip install -r requirements.txt` 成功
- [ ] `backend/.env` 已创建（`LLM_MODE=mock` 即可本地演示）
- [ ] `uvicorn app.main:app --reload` 可访问 `/health`
- [ ] `POST /api/travel/query` 返回 `answer` + `visible_trace` + `evidence_summary`
- [ ] `cd backend && pytest -q` 全部通过
- [ ] 上传前确认 `.env` 未被 `git add`
- [ ] GitHub 空仓库已创建（若使用默认 RemoteUrl）
- [ ] 已配置 PAT 或运行 `setup_project_credentials.ps1`
- [ ] `.\upload_to_github.ps1` 推送成功

---

*文档版本：与当前 `backend/app` MVP + GitHub 上传脚本实现一致。若 API 或环境变量有变更，以代码为准并同步更新本 Runbook。*
