# Crawler Provider Wrappers

本地 subprocess 包装器，对接第三方爬虫仓库输出 JSON。本仓库**不负责**安装 CtripSpider / dianping-crawler 等上游项目。

## 边界

- 不下单、不支付、不登录、不管理 Cookie
- 只调用用户在 `.env` 中配置的本地 CLI
- pytest 默认不执行外部 crawler；联调使用 `scripts/smoke/`

## 通用契约

### 命令占位符

`CTRIP_CRAWLER_COMMAND` / `DIANPING_CRAWLER_COMMAND` / `FLIGGY_TICKET_CRAWLER_COMMAND` 支持：

| 占位符 | 含义 |
|--------|------|
| `{place}` | 景点/商户名 |
| `{city}` | 城市 |
| `{country}` | 国家 |
| `{query}` | 搜索词（默认同 place） |
| `{claim_type}` | S5 信息需求 |

### stdout JSON（最小）

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

非 JSON 输出会尝试宽松解析（`output_parse_status=non_json`）；完全失败则 0 条 evidence。

### BaseCrawlerTool

- `is_configured()`：`enabled` 且 `command` 非空
- `build_command()` / `run_subprocess()` / `parse_output()` 公开 API
- 超时返回结构化错误，不抛未捕获异常

---

## 携程 CtripSpider

| 项 | 值 |
|----|-----|
| 参考仓库 | `aglorice/CtripSpider`（`CTRIP_CRAWLER_REPO`） |
| 工具 | `ctrip_review_crawler_mcp`, `ctrip_ticket_signal_crawler_mcp` |
| 开关 | `CTRIP_CRAWLER_ENABLED=true`, `ENABLE_REVIEW_CRAWLER_PROVIDERS` / `ENABLE_TICKET_CRAWLER_PROVIDERS` |
| **内置路径（默认）** | `CTRIP_WEBSEARCH_SIGNAL_ENABLED=true` + `MCP_SEARCH_ENABLED` → 经 open-webSearch 检索 `site:ctrip.com` 信号，**无需**本地 CLI |

**定位**：景区评论与体验信号；票价提及仅 `ticket_price_candidate`。

**可选 subprocess**（覆盖内置路径）：

```env
CTRIP_CRAWLER_COMMAND=python path/to/ctrip_cli.py --place "{place}" --city "{city}"
```

**Smoke**：

```bash
cd scripts/smoke
python check_ctrip_crawler.py --place "可可托海景区" --city "阿勒泰"
```

---

## 大众点评 dianping-crawler

| 项 | 值 |
|----|-----|
| 参考仓库 | `crazyboycjr/dianping-crawler`（`DIANPING_CRAWLER_REPO`） |
| 工具 | `dianping_review_crawler_mcp`, `dianping_ticket_signal_crawler_mcp` |
| 开关 | `DIANPING_CRAWLER_ENABLED=true`, `ENABLE_REVIEW_CRAWLER_PROVIDERS` / `ENABLE_TICKET_CRAWLER_PROVIDERS` |
| **内置路径（默认）** | `DIANPING_WEBSEARCH_SIGNAL_ENABLED=true` + `MCP_SEARCH_ENABLED` → 经 open-webSearch 检索 `site:dianping.com` 信号，**无需**本地 CLI |

**定位**：评论信号、价值感、排队/拥挤、商业化、票务渠道提及；非官方票价强事实。

**可选 subprocess**：

```env
DIANPING_CRAWLER_COMMAND=python path/to/dianping_cli.py --place "{place}" --city "{city}"
```

**关键词**（normalizer 侧）：门票、团购、预约、排队、性价比、商业化、亲子、老人等。

**Smoke**：

```bash
python check_dianping_crawler.py --place "可可托海景区"
```

---

## 飞猪

| 路径 | 配置 | 工具 |
|------|------|------|
| **FlyAI（推荐）** | `FLIGGY_FLYAI_API_KEY`（[飞猪AI开放平台](https://flyai.open.fliggy.com/console)） | `fliggy_ticket_snapshot_crawler_mcp` |
| subprocess 回退 | `FLIGGY_TICKET_CRAWLER_COMMAND` | 同上 |
| 评论信号 | subprocess only | `fliggy_ticket_review_signal_mcp` |

FlyAI 通过 `npx @fly-ai/flyai-cli` 调用 `search-poi` / `keyword-search`，需本机 Node.js。

**Smoke**：

```bash
python check_fliggy_crawler.py --place "禾木景区" --city "阿勒泰"
```

---

## 价格与信号层级

| 层级 | 来源 | Coverage |
|------|------|----------|
| Strong | 官方页 / 搜索明确票价 | 可满足 required `ticket_price` |
| Partial | TicketLens / 飞猪 / 平台候选价 | 仅 `ticket_price_candidate` |
| Review mention | 携程/点评评论中的票价词 | 不覆盖 required `ticket_price` |
| Historical | `TicketSnapshotStore` | 仅历史参考 |

详见 [ticketing-mcp-providers.md](ticketing-mcp-providers.md)。

---

## 内置 CLI 包装器（subprocess 优先）

仓库提供统一 JSON stdout 契约，对接外部 git 爬虫或 HTTP 回退：

| CLI | 工具 policy | `--mode` |
|-----|-------------|----------|
| `scripts/crawlers/ctrip_cli.py` | `ctrip_review_crawler_mcp`, `ctrip_ticket_signal_crawler_mcp`, `ctrip_guide_crawler_mcp`, crowd 子信号 | `review`, `ticket`, `guide`, `crowd` |
| `scripts/crawlers/dianping_cli.py` | `dianping_review_crawler_mcp`, `dianping_nearby_crawler_mcp` | `review`, `nearby`, `ticket` |

推荐 `.env`：

```env
CTRIP_CRAWLER_COMMAND=python ../../scripts/crawlers/ctrip_cli.py --place "{place}" --city "{city}" --mode {mode}
DIANPING_CRAWLER_COMMAND=python ../../scripts/crawlers/dianping_cli.py --place "{place}" --city "{city}" --mode review
DIANPING_SPIDER_COMMAND=python ../../scripts/crawlers/dianping_cli.py --place "{place}" --city "{city}" --mode nearby
ENABLE_TRAVEL_NOTE_CRAWLERS=true
ENABLE_NEARBY_PLATFORM_CRAWLERS=true
ENABLE_CROWD_ESTIMATION_TOOLS=true
```

外部仓库（可选，设置 `CTRIP_SPIDER_ROOT` / `DIANPING_CRAWLER_ROOT` 后 CLI 会优先调用其 `run_place_query.py`）：

- `aglorice/CtripSpider` — 评论/热度
- `crazyboycjr/dianping-crawler` — 店铺评论 JSON
- `Sniper970119/dianping_spider` — 搜索型附近 POI（经 `DIANPING_SPIDER_COMMAND`）

`crowd_estimation_mcp` 为组合 Provider（携程 crowd + 点评排队 + 百度路况），非独立 CLI。

Smoke：

```bash
python scripts/smoke/check_ctrip_guide_crawler.py --place "喀纳斯" --city "阿勒泰"
python scripts/smoke/check_dianping_nearby_crawler.py --place "喀纳斯"
python scripts/smoke/check_crowd_estimation.py --place "喀纳斯" --city "阿勒泰"
```
