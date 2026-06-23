# 票务 / 评论 Provider（第一批）

本文档说明 TicketLens、携程 / 飞猪 / 大众点评爬虫包装器与票价快照库的边界、配置与手动验收方式。

## 1. 定位

| 类型 | 工具名 | 输出 |
|------|--------|------|
| TicketLens REST | `ticketlens_experience_mcp` | 票价候选、订票渠道、票种 |
| TicketLens 评论 | `ticketlens_experience_review_signal_mcp` | 评论摘要、评分信号 |
| 携程爬虫 | `ctrip_review_crawler_mcp`, `ctrip_ticket_signal_crawler_mcp` | 评论 / 票务提及 |
| 飞猪 Open API / 爬虫 | `fliggy_ticket_snapshot_crawler_mcp`, `fliggy_ticket_review_signal_mcp` | 票价候选 + 快照（API 或 CLI） |
| 大众点评爬虫 | `dianping_review_crawler_mcp`, `dianping_ticket_signal_crawler_mcp` | 评论 / 票务提及 |
| 快照库 | `ticket_snapshot_store`, `ticket_price_history_query` | 历史票价 `HISTORICAL_TICKET_SNAPSHOT` |

所有结果统一归一化为 `Evidence[]`，经 S5 `ToolWhitelistBuilder` → `ActionExecutor` 调用。

## 2. 明确不做

- 不下单、不支付、不登录、不管理 Cookie
- pytest **不**发起真实 HTTP / subprocess（仅配置、归一化、快照、Coverage、PolicyGuard）
- 外部联调使用 `scripts/smoke/` 手动脚本

## 3. 配置开关（`.env.example` 默认全 `false`）

仅 `TICKET_SNAPSHOT_STORE_ENABLED=true` 默认开启。在本地 `.env` 按需打开：

```env
TICKETLENS_ENABLED=true
TICKETLENS_API_BASE_URL=https://api.ticketlens.com/v1
TICKETLENS_API_KEY=your-key

ENABLE_TICKET_CRAWLER_PROVIDERS=true
ENABLE_REVIEW_CRAWLER_PROVIDERS=true

CTRIP_CRAWLER_ENABLED=true
CTRIP_CRAWLER_COMMAND=python path/to/ctrip_cli.py --place "{place}" --city "{city}"

FLIGGY_TICKET_CRAWLER_ENABLED=true
ENABLE_TICKET_CRAWLER_PROVIDERS=true
FLIGGY_FLYAI_API_KEY=sk-你的密钥

DIANPING_CRAWLER_ENABLED=true
DIANPING_CRAWLER_COMMAND=...
```

粗粒度 `ENABLE_TICKET_PLATFORM_CRAWLERS` 仍作用于**未实现**的旧 placeholder（`ctrip_ticket_crawler_mcp` 等）；新 provider 走 per-provider 开关。

## 4. 价格层级（Coverage）

| 层级 | Claim | 能否满足 required `ticket_price` |
|------|-------|----------------------------------|
| Strong | `ticket_price`（官方/搜索明确票价） | 是 |
| Partial | `ticket_price_candidate` / `price_candidate`（TicketLens、飞猪、平台候选） | 否 |
| None | 评论、`ticket_related_mentions` 无结构化价 | 否 |

## 5. 爬虫 stdout 最小 JSON 契约

```json
{
  "items": [
    {
      "review_summary": "…",
      "positive_aspects": ["…"],
      "negative_aspects": ["…"],
      "ticket_related_mentions": ["门票128元"],
      "price_text": "¥128起",
      "source_url": "https://…",
      "confidence": 0.6
    }
  ]
}
```

命令行支持占位符：`{place}` `{city}` `{country}` `{query}` `{claim_type}`。

## 6. 快照积累

TicketLens / 飞猪解析到价格时自动 `save_snapshot`（`snapshot_saved_count` 写入 `ToolTrace`）。历史查询走 `ticket_price_history_query`。

## 7. S5 信息域绑定

- **ticket_booking**：primary 含 `ticketlens_experience_mcp`；platform 含飞猪/携程/点评信号爬虫；enrichment 含快照读写。
- **review_signal**：`ctrip_review_crawler_mcp`、`dianping_review_crawler_mcp`、`fliggy_ticket_review_signal_mcp`、TicketLens 评论工具。

## 8. 手动 Smoke

```bash
cd apps/agent-python
python ../../scripts/smoke/check_ticketlens.py --place "可可托海景区" --city "阿勒泰"
python ../../scripts/smoke/check_ctrip_crawler.py --place "南京博物院" --city "南京"
python ../../scripts/smoke/check_fliggy_crawler.py --place "西湖" --city "杭州"
python ../../scripts/smoke/check_dianping_crawler.py --place "外滩" --city "上海"
```

输出：`enabled` / `configured` / `success` / evidence 条数 / 首条 claim 摘要。

## 9. 单元测试

```bash
cd apps/agent-python
python -m compileall app
pytest app/evals/ticket_provider_tests.py app/evals/s5_information_domain_tests.py -q
```

## 10. 飞猪AI开放平台（推荐）

凭证来自 [飞猪AI开放平台](https://flyai.open.fliggy.com/console) → **接口密钥**（`sk-` 开头，**仅此一个**，没有 Secret）。

```env
ENABLE_TICKET_CRAWLER_PROVIDERS=true
FLIGGY_TICKET_CRAWLER_ENABLED=true
FLIGGY_FLYAI_ENABLED=true
FLIGGY_FLYAI_API_KEY=sk-你的密钥
```

底层通过 `@fly-ai/flyai-cli` 调用官方 MCP 服务：`search-poi`（有城市时）或 `keyword-search`（无城市时）。

需本机已安装 **Node.js**（默认 `npx @fly-ai/flyai-cli`）。

### 传统淘宝 TOP（可选）

若你是 ISV/商家，走 [open.fliggy.com](https://open.fliggy.com) 应用管理的 **App Key + App Secret**，设置 `FLIGGY_TOP_API_ENABLED=true`。

## 11. 旧 placeholder

`ctrip_ticket_crawler_mcp`、`fliggy_ticket_crawler_mcp`、`dianping_ticket_crawler_mcp` 仍注册为 deprecated placeholder，避免破坏历史 trace；请迁移到新工具名。
