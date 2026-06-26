# Evidence-first Travel Intelligence Agent — 仓库说明

本仓库为 **东亚三国（日本 / 中国 / 韩国）Evidence-first 旅游情报 Agent** Monorepo。

## 快速入口

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

详见 [RUNBOOK.md](RUNBOOK.md)、[README.md](README.md)、[REPO_MAP.md](REPO_MAP.md)。

## 开发约定

- 工具必须返回 `Evidence` 对象，Composer 只基于 evidence 总结
- 首期仅支持 Japan / China / South Korea
- mock 数据真相源：`packages/tools/mock/data.py`
- 状态链：`apps/agent-python/app/orchestrator/state_machine.py`
- 调试日志：`apps/agent-python/debug_last_session.md`
