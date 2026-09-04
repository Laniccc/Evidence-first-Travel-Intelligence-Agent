# 批次 B 验证与交接

日期：2026-09-04。范围：Task 4–6。分支：codex/resume-capability-closure。
executing-plans 检查点：7/15 tasks 完成；停止在批次 B，不执行 C，不推送或合并。

## Task 4：有界并行检索

- 生产 HybridRetrievalHandler 使用 await aretrieve，lexical/dense 同时启动，各自 2 秒默认超时。
- BoundedIO 为 lexical/dense/postfilter 提供独立串行 lane，每 lane 默认最多 2 个已提交任务（含运行中）。
  拒绝超额提交；超时和取消不释放尚在运行的同步任务容量。真实 future 完成后才释放。
- Qdrant dense 使用专用 lane；融合和 SQLite 二次过滤在 postfilter lane 完成。
- FastAPI 退出先 await 工作队列 drain，再关闭 Qdrant。同步 close 保留给同步资源拥有者。
- 验证：barrier 同时抵达、单/双失败、取消、超时后容量保留、真实持久 Qdrant local 重建索引及两次请求独立报告。
- 同步 retrieve 保留给原离线评测；运行中状态不再直接调用同步检索。

## Task 5：标准 MCP stdio

- 固定 Python mcp==1.29.1，固定 @baidumap/mcp-server-baidu-map==1.0.5，提交完整 npm lockfile。
- 查询元数据和安装经过网络权限审核。新 Python 依赖装在 ignored .venv-batch-b，使用 system-site-packages，不更改全局 Python。
  npm 安装禁用 scripts；没有启动真实百度 Server。
- 单 owner task 创建/退出 SDK stdio 与 ClientSession；每次调用通过有界队列投递，避免跨任务退出 AnyIO cancel scope。
- 工具发现最多 3 页/128 个条目/256 KiB，调用参数最多 16 KiB，结果对象最多 64 KiB。
  Schema 只接受本地简单结构，拒绝引用；刷新或重连发现 Schema 变化即拒绝。
- 只允许 map_search_places / map_place_details，参数先验证后提交；isError、429、EOF、超时、大小越界分类。
- stderr 使用操作系统空设备排空，保留量为 0；SDK 诊断清除 payload/异常正文。
- Windows 使用 SDK 的隐藏进程启动与进程树清理。正常退出、发现失败、工具失败、取消后均通过 PID 存活检查。

## Task 6：地图信息到临时证据

- 唯一可信实体绑定由注入的 catalog/operator resolver 提供，不由模型指定。包含景点 ID、名字/别名、城市，可选预绑定 UID。
- 无 UID 时 search，唯一名称/城市匹配后 detail；有可信 UID 时跳过 search。详情再次核对 UID/名称/城市。
- 只使用返回的 detail_info.detail_url，校验地图域、POI UID、HTTP(S)、无凭据；缺少来源不伪造替代链接。
- 当前仅开放两种事实映射：address → general_description；detail_info.shop_hours → opening_hours。
  未提供字段为证据不足；不把 detail_info 的消费价格当门票，不推断预约或无障碍事实。
- 保存原字段的 JSON Pointer、原值、来源、schema/payload/content hash、retrieval time 和 1 小时保守 TTL。
  TTL 不是未来事实保证；历史/未来指定时间不调用当前快照路径。
- 一次 logical gap 与实际 tools/call 分开计数；每工具最多 2 attempts，总上限 4，工具默认 5 秒，总 deadline 20 秒，
  外层 gap 状态 25 秒。timeout/connection failure 最多重建一次会话；不做整链外层重试。
- 比较时依据缺失 claim 的 subtask 定位景点，已有其他景点的产物保持不变。
- 失败返回 Evidence Evaluate，状态标记 recovered，记录 gap_unavailable/gap_retried、失败类型和调用明细；不发布知识、不同步索引。
- 为守住分层，将 MCP envelope 移入 app/contracts/mcp_evidence.py，更新引用；未添加跨层兼容桥。

## 可复现验证

以下在 apps/agent-python 运行；报告写 ignored generated，不覆盖原提交报告。

```powershell
./.venv-batch-b/Scripts/python.exe -m pytest -q
./.venv-batch-b/Scripts/python.exe -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-b-final.json
```

- 执行前：188 passed / 1 skipped。
- Task 4：并行专项 6 passed；此前 retrieval + state + composition root + layer 检查 53 passed。
- Task 5：协议专项 13 passed；合并架构/scope 检查 25 passed。
- Task 6：百度 + legacy gap 测试 14 passed，包含独立 stdio 子进程 → adapter → normalizer → Evidence。
- 最终全量：219 passed / 1 skipped；原 13 个 gate 全通过。
- 保留真实 Qdrant server opt-in skip 和原 Starlette/httpx 弃用警告；Java/Web 公共 DTO 未改，未重跑 Java/Web。
- 旧 gap 测试 used_tool_calls 从 1 改为 2：同一逻辑任务实际尝试两次，修正计数语义，不放宽安全上限。

## 仍未完成 / 限制

- 并行检索已生产装配；LLM/MCP 在线入口、readiness、统一外部生命周期属于 Task 10，不能声称百度真实接入已验收。
- 同步线程无法强杀：容量保持有界，关闭会等待实际任务结束；永久阻塞底层调用仍会阻碍 shutdown。
- SDK 负责换行分帧；结果大小检查在 SDK 解析后进行，不宣称已实现 raw stdout 字节级内存硬上限。
- 源码固定包仅检查和锁定，不运行真实百度 Server。真实 AK/数据留存许可均未使用或假设；知识晋升保持未实施。
- 原评测是受控 hash-embedding 场景；新增协议/故障测试不是线上语义召回或真实模型质量指标。
- 下一批 C：Task 7–10（候选验证、版本安全、原子发布/索引待办、生产接线）。

## 核对的官方依据

- [Python SDK 与 v1 维护说明](https://github.com/modelcontextprotocol/python-sdk)
- [固定 Python SDK 发布](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.29.1)
- [百度官方工具与包说明](https://github.com/baidu-maps/mcp)
- npm 元数据与本地固定 1.0.5 包 dist/index.js：search/query/region、detail/uid/scope，
  以及结果 address/city/uid/detail_info 字段。没有根据旧广域 adapter 猜测返回值。
