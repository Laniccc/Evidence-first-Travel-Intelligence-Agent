# External Crawlers

本目录存放**第三方爬虫仓库**与本项目维护的 **place-query 适配器**。

## 目录结构

```text
external/crawlers/
  vendors/                 # git clone（不提交）
    CtripSpider/           # aglorice/CtripSpider
    dianping-crawler/      # crazyboycjr/dianping-crawler
  ctrip/run_place_query.py # 携程单点查询适配器（CLI 入口）
  dianping/run_place_query.py
  _adapter_common.py
```

## 一键安装

仓库根目录：

```powershell
.\scripts\crawlers\install-deps.ps1
```

会克隆两个 vendor 仓库、安装 CtripSpider Python 依赖，并打印/写入 `.env` 推荐项。

## `.env` 关键项（`apps/agent-python/.env`）

```env
CTRIP_CRAWLER_ENABLED=true
DIANPING_CRAWLER_ENABLED=true
ENABLE_REVIEW_CRAWLER_PROVIDERS=true
ENABLE_NEARBY_PLATFORM_CRAWLERS=true

CTRIP_SPIDER_ROOT=../../external/crawlers/ctrip
DIANPING_CRAWLER_ROOT=../../external/crawlers/dianping

CTRIP_CRAWLER_COMMAND=python ../../scripts/crawlers/ctrip_cli.py --place "{place}" --city "{city}" --mode {mode}
DIANPING_CRAWLER_COMMAND=python ../../scripts/crawlers/dianping_cli.py --place "{place}" --city "{city}" --mode {mode}

CRAWLER_PROXY_URL=http://127.0.0.1:7890
CRAWLER_FETCH_TIMEOUT_SECONDS=15
```

`ctrip_cli` / `dianping_cli` 会**优先**调用上述 `*_ROOT` 下的 `run_place_query.py`，失败再 HTTP 回退。

## Smoke

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
$env:PYTHONIOENCODING = "utf-8"
python ../../scripts/smoke/check_ctrip_crawler.py --place "明故宫" --city "南京"
python ../../scripts/smoke/check_dianping_crawler.py --place "明故宫" --city "南京"
python ../../scripts/smoke/check_dianping_nearby_crawler.py --place "明故宫" --city "南京"
```

## 说明

- `vendors/dianping-crawler` 为 Node 批量爬虫，需阿布云代理；日常由 `dianping/run_place_query.py` 负责单点查询。
- `vendors/CtripSpider` 提供评论 API；适配器在配置 `CRAWLER_PROXY_URL` 时会注入代理。
- 改 `.env` 后需重启 uvicorn。
- **Agent 默认关闭携程/点评爬虫**（反爬/噪声）；勿在未 smoke 通过前打开 `CTRIP_CRAWLER_ENABLED` / `DIANPING_CRAWLER_ENABLED`。
