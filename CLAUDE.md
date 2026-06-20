# Evidence-first Travel Intelligence Agent — 仓库说明

本仓库为 **东亚三国（日本 / 中国 / 韩国）Evidence-first 旅游情报 Agent** MVP。

## 快速入口

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

详见 [RUNBOOK.md](RUNBOOK.md)、[README.md](README.md)。

## 开发约定

- 工具必须返回 `Evidence` 对象，Composer 只基于 evidence 总结
- 首期仅支持 Japan / China / South Korea
- mock 数据在 `backend/app/tools/mock_data.py`
- 状态链在 `backend/app/orchestrator/state_machine.py`
