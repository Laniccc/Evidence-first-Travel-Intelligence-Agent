# Evidence-first Agentic RAG Revised Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** 将现有旅行 Agent 收敛为只支持景点事实、适合度、比较和澄清的可审计 Agentic RAG，并用 SQLite 版本治理、Qdrant 向量索引、混合检索、Claim 引用和离线 Eval 形成完整技术闭环。

**Architecture:** SQLite 是景点知识的唯一事实源，管理 source、document version、fact chunk、FTS5 和索引同步状态；Qdrant 是可重建的 dense vector 派生索引。类型化 `RetrievalPlan` 驱动 lexical+dense 召回、RRF、active-version post-filter 和确定性 rerank，并通过唯一状态运行时进入 Evidence Evaluate、Compose 与 Citation Guard。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、SQLite/FTS5、Qdrant 1.19、qdrant-client、pytest；Java 21/Spring Boot 3.4；Vite/Node test；Docker Compose；GitHub Actions。

---

## 执行前提

以下任务已在 `codex/evidence-agent-consolidation` 分支完成，不得重做：

| Task | Commit | 结果 |
|---|---|---|
| 基线与 API 边界 | `3815b85` | session_id 透传，debug opt-in，Python/Java/Web 基线 |
| 显式状态运行时 | `8fb06e8` | 静态转移、超时、有限重试、最大步数、审计事件 |
| SQLite 知识生命周期 | `5754209` | document version、hash 幂等、publish/supersede/expire、CLI |

修订设计：`docs/plans/2026-09-02-agentic-rag-revision-design.md`。

实施约束：

- 不实现 Neo4j、知识图谱或 GraphRAG。
- 不把 Qdrant 当作知识事实源；所有命中必须回查 SQLite active version。
- 默认测试和快速 Eval 不访问外网、不调用真实 LLM、不下载真实 embedding model。
- 真实中文 embedding 只用于手动 quality profile。
- 所有行为修改先写失败测试，再写最小实现。
- 每个 Task 独立提交；批次完成后运行 Python 全量测试。

## Task 4：Qdrant 向量索引与 Embedding 端口

**Files:**

- Create: `infra/qdrant/compose.yml`
- Create: `apps/agent-python/app/evidence/retrieval/__init__.py`
- Create: `apps/agent-python/app/evidence/retrieval/contracts.py`
- Create: `apps/agent-python/app/evidence/retrieval/embedding.py`
- Create: `apps/agent-python/app/integrations/qdrant/__init__.py`
- Create: `apps/agent-python/app/integrations/qdrant/vector_index.py`
- Create: `apps/agent-python/tests/retrieval/test_embedding.py`
- Create: `apps/agent-python/tests/retrieval/test_qdrant_vector_index.py`
- Modify: `apps/agent-python/requirements.txt`
- Modify: `apps/agent-python/app/config.py`
- Modify: `apps/agent-python/.env.example`
- Modify: `.gitignore`

**Step 1: 写失败的 Embedding 和向量索引测试**

测试端口与离线 fake：

```python
def test_deterministic_embedder_is_stable_and_normalized():
    embedder = DeterministicHashEmbedding(dimension=16)
    first = embedder.embed_query("故宫是否需要预约")
    second = embedder.embed_query("故宫是否需要预约")

    assert first == second
    assert len(first) == 16
    assert sum(value * value for value in first) == pytest.approx(1.0)
```

测试 Qdrant local mode：

```python
def test_qdrant_index_filters_by_attraction_and_fact_type():
    client = QdrantClient(":memory:")
    index = QdrantVectorIndex(client, collection="attraction-facts-test", dimension=4)
    index.recreate()
    index.upsert([point("chunk-1", [1, 0, 0, 0], attraction="forbidden-city", fact="reservation")])

    hits = index.search(
        [1, 0, 0, 0],
        filters=VectorFilters(
            attraction_ids=["forbidden-city"],
            fact_types=["reservation"],
        ),
        limit=3,
    )

    assert [hit.chunk_id for hit in hits] == ["chunk-1"]
```

还需覆盖：任意字符串 `chunk_id` 稳定映射为 UUID point ID、payload round trip、collection dimension 不匹配时 fail closed、limit 上限为 20。

**Step 2: 运行并确认失败**

Run:

```powershell
cd apps/agent-python
pytest tests/retrieval/test_embedding.py tests/retrieval/test_qdrant_vector_index.py -q
```

Expected: collection/import failure because retrieval package and qdrant-client do not exist.

**Step 3: 添加依赖与配置**

`requirements.txt` 增加：

```text
qdrant-client[fastembed]>=1.15,<2
```

配置增加：

```python
qdrant_mode: Literal["local", "server"] = "local"
qdrant_url: str = "http://127.0.0.1:6333"
qdrant_api_key: str | None = None
qdrant_collection: str = "attraction-facts"
embedding_mode: Literal["deterministic", "fastembed"] = "deterministic"
embedding_model: str = "BAAI/bge-small-zh-v1.5"
embedding_dimension: int = 512
vector_search_limit: int = 20
```

`qdrant_api_key` 必须加入空字符串转 `None` validator，日志不得输出其值。

**Step 4: 实现端口与 adapter**

`contracts.py` 定义：

```python
class VectorPoint(BaseModel):
    chunk_id: str
    vector: list[float]
    attraction_id: str
    fact_type: str
    document_version_id: str
    content_hash: str
    corpus_version: str

class VectorFilters(BaseModel):
    attraction_ids: list[str] = Field(min_length=1)
    fact_types: list[str] = Field(default_factory=list)
    corpus_version: str | None = None

class VectorHit(BaseModel):
    chunk_id: str
    score: float
    payload: dict
```

`embedding.py` 定义 `EmbeddingProvider` Protocol 和只供测试/离线功能验证的 `DeterministicHashEmbedding`。真实 adapter 使用 FastEmbed，但 import 必须 lazy，模型不可用时抛出 typed `EmbeddingUnavailableError`。

`QdrantVectorIndex` 只暴露 `recreate/upsert/delete/search/count/health`，所有 search 强制 payload、limit 和 filter。

**Step 5: 配置 Qdrant Docker Compose**

`infra/qdrant/compose.yml` 使用固定镜像：

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.19.0
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:-local-dev-key}
    volumes:
      - qdrant_storage:/qdrant/storage
volumes:
  qdrant_storage:
```

本地端口不得绑定 `0.0.0.0`，volume 与 `.env` 不提交。

**Step 6: 安装依赖并运行测试**

Run:

```powershell
pip install -r requirements.txt
pytest tests/retrieval/test_embedding.py tests/retrieval/test_qdrant_vector_index.py -q
python -m compileall -q app
```

Expected: all tests pass; compileall exits 0.

可选真实服务 smoke test：

```powershell
docker compose -f ../../infra/qdrant/compose.yml up -d
python -c "from qdrant_client import QdrantClient; print(QdrantClient(url='http://127.0.0.1:6333', api_key='local-dev-key').get_collections())"
```

**Step 7: Commit**

```powershell
git add .gitignore infra/qdrant apps/agent-python/requirements.txt apps/agent-python/.env.example apps/agent-python/app/config.py apps/agent-python/app/evidence/retrieval apps/agent-python/app/integrations/qdrant apps/agent-python/tests/retrieval
git commit -m "feat: add qdrant vector index boundary"
```

## Task 5：索引 generation、一致性和重建 CLI

**Files:**

- Modify: `apps/agent-python/app/evidence/knowledge/schema.sql`
- Modify: `apps/agent-python/app/evidence/knowledge/models.py`
- Modify: `apps/agent-python/app/evidence/knowledge/repository.py`
- Modify: `apps/agent-python/app/evidence/knowledge/cli.py`
- Create: `apps/agent-python/app/evidence/retrieval/index_sync.py`
- Create: `apps/agent-python/tests/knowledge/test_index_generation.py`
- Create: `apps/agent-python/tests/knowledge/test_index_sync.py`

**Step 1: 写失败的 generation tests**

```python
def test_failed_rebuild_never_replaces_active_generation(repo, vector_index):
    old = repo.start_index_generation("corpus-1", "fake-v1")
    repo.complete_index_generation(old.generation_id, indexed_chunk_count=3)
    failing = IndexSynchronizer(repo, vector_index=FailingVectorIndex(), embedder=FakeEmbedding())

    result = failing.rebuild(corpus_version="corpus-2")

    assert result.status == "failed"
    assert repo.active_index_generation().generation_id == old.generation_id

def test_rebuild_is_idempotent_for_same_chunk_hash(...): ...
def test_superseded_chunk_is_removed_from_vector_index(...): ...
```

**Step 2: 运行并确认失败**

Run: `pytest tests/knowledge/test_index_generation.py tests/knowledge/test_index_sync.py -q`

Expected: FAIL because generation tables and synchronizer do not exist.

**Step 3: 扩展 SQLite schema**

新增 `index_generation` 与 `chunk_index_state`，状态 CHECK 必须与修订设计一致。`repository.py` 增加：

```python
list_active_chunks(as_of: datetime) -> list[IndexableChunk]
start_index_generation(corpus_version: str, embedding_model: str) -> IndexGeneration
mark_chunk_indexed(...)
fail_index_generation(...)
complete_index_generation(...)
active_index_generation() -> IndexGeneration | None
```

完成 generation 的事务必须先将旧 active 标记为 superseded，再激活新 generation。

**Step 4: 实现 IndexSynchronizer**

固定顺序：读取 active chunks → 批量 embedding → Qdrant upsert → 删除旧 generation points → count/hash consistency check → 激活 generation。任何异常先写 failed generation，再抛出 typed failure；不得吞异常。

**Step 5: 扩展 CLI**

```powershell
python -m app.evidence.knowledge.cli reindex --db data/knowledge.sqlite3 --qdrant-mode local
python -m app.evidence.knowledge.cli inspect --db data/knowledge.sqlite3 --index
```

输出 corpus version、embedding model、indexed/failed/deleted counts，不输出向量。

**Step 6: 运行测试**

Run:

```powershell
pytest tests/knowledge/test_repository.py tests/knowledge/test_lifecycle.py tests/knowledge/test_index_generation.py tests/knowledge/test_index_sync.py -q
python -m app.evidence.knowledge.cli --help
```

Expected: pass; CLI includes `reindex` and index inspection.

**Step 7: Commit**

```powershell
git add apps/agent-python/app/evidence/knowledge apps/agent-python/app/evidence/retrieval/index_sync.py apps/agent-python/tests/knowledge
git commit -m "feat: govern vector index generations"
```

## Task 6：Hybrid Retriever、RRF 与确定性重排

**Files:**

- Create: `apps/agent-python/app/evidence/retrieval/report.py`
- Create: `apps/agent-python/app/evidence/retrieval/lexical.py`
- Create: `apps/agent-python/app/evidence/retrieval/fusion.py`
- Create: `apps/agent-python/app/evidence/retrieval/reranker.py`
- Create: `apps/agent-python/app/evidence/retrieval/hybrid.py`
- Create: `apps/agent-python/tests/retrieval/test_lexical.py`
- Create: `apps/agent-python/tests/retrieval/test_fusion.py`
- Create: `apps/agent-python/tests/retrieval/test_hybrid.py`
- Modify: `apps/agent-python/app/evidence/evidence_model.py`
- Modify: `contracts/schemas/evidence.schema.json`

**Step 1: 写失败的召回、融合和降级测试**

```python
def test_rrf_rewards_candidates_found_by_both_channels():
    fused = reciprocal_rank_fusion(
        lexical=[hit("a"), hit("b")],
        dense=[hit("b"), hit("c")],
        rrf_k=60,
    )
    assert fused[0].chunk_id == "b"

def test_qdrant_timeout_recovers_with_lexical_only(seed_store):
    retriever = HybridRetriever(
        lexical=SQLiteLexicalRetriever(seed_store),
        dense=FailingDenseRetriever("timeout"),
    )
    report = retriever.retrieve(plan_for("故宫预约"))
    assert report.degradation == "lexical_only"
    assert report.dense_attempt.failure_code == "timeout"
    assert report.final_hits
```

必须覆盖：dense-only、lexical-only、both empty、stale Qdrant point、pending/superseded/expired leakage、fact type filter、attraction filter、top_k limit、comparison subtask isolation。

**Step 2: 运行并确认失败**

Run: `pytest tests/retrieval/test_lexical.py tests/retrieval/test_fusion.py tests/retrieval/test_hybrid.py -q`

**Step 3: 实现 RetrievalPlan 和 RetrievalReport**

`contracts.py` 增加：

```python
class RetrievalPlan(BaseModel):
    task_type: Literal["fact_query", "suitability", "comparison"]
    query_text: str
    attraction_ids: list[str] = Field(min_length=1, max_length=2)
    fact_types: list[FactType] = Field(default_factory=list)
    as_of: datetime
    top_k: int = Field(default=3, ge=1, le=5)
    subtask_id: str
```

`RetrievalReport` 必须包含 lexical/dense attempt、fusion、post-filter reject reason、final hits、degradation、corpus/index/model version 和 latency breakdown。零命中也返回完整 report。

**Step 4: 实现 lexical、fusion、post-filter 和 rerank**

- FTS5 召回上限 20。
- dense 召回上限 20。
- RRF `k=60`。
- fusion 后只保留前 8。
- 回查 SQLite active version 后重排。
- 默认权重：RRF .60、source .20、freshness .15、fact-type .05。

任何未通过 SQLite 校验的 point 必须进入 `post_filter_rejections`，原因只允许 `pending_version/superseded_version/expired_version/hash_mismatch/missing_chunk`。

**Step 5: 扩展 Evidence provenance**

```python
class EvidenceProvenance(BaseModel):
    source_id: str
    document_version_id: str
    chunk_id: str
    content_hash: str
    locator: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    retrieval_channels: list[Literal["lexical", "dense"]]
    retrieval_score: float
    corpus_version: str
```

同步更新 JSON schema。

**Step 6: 运行测试**

Run:

```powershell
pytest tests/retrieval -q
pytest tests/test_agent_evidence_layer.py tests/test_agent_contract_layer.py -q
```

Expected: all pass.

**Step 7: Commit**

```powershell
git add apps/agent-python/app/evidence/retrieval apps/agent-python/app/evidence/evidence_model.py apps/agent-python/tests/retrieval contracts/schemas/evidence.schema.json
git commit -m "feat: add hybrid evidence retrieval"
```

## Task 7：RAG fixture、检索消融与版本 Eval

**Files:**

- Create: `apps/agent-python/evals/fixtures/knowledge.json`
- Create: `apps/agent-python/evals/datasets/retrieval.jsonl`
- Create: `apps/agent-python/evals/datasets/versioning.jsonl`
- Create: `apps/agent-python/evals/graders/__init__.py`
- Create: `apps/agent-python/evals/graders/retrieval.py`
- Create: `apps/agent-python/evals/graders/versioning.py`
- Create: `apps/agent-python/evals/runner.py`
- Create: `apps/agent-python/tests/evals/test_retrieval_grader.py`
- Create: `apps/agent-python/tests/evals/test_versioning_grader.py`

**Step 1: 写失败的 grader tests**

```python
def test_retrieval_metrics_are_computed_from_ranked_chunk_ids():
    metrics = grade_retrieval(
        [case(expected_chunk_ids=["c2"], ranked_chunk_ids=["c1", "c2", "c3"])]
    )
    assert metrics.recall_at_3 == 1.0
    assert metrics.mrr == 0.5

def test_expired_hit_fails_version_suite():
    metrics = grade_versioning([case(status="expired", returned=True)])
    assert metrics.expired_leakage_rate == 1.0
```

**Step 2: 运行并确认失败**

Run: `pytest tests/evals/test_retrieval_grader.py tests/evals/test_versioning_grader.py -q`

**Step 3: 创建最小语料**

固定为 8 个景点、60–100 active chunks、12 个 superseded/expired、8 个 pending/rejected、6 组冲突和 5 个更新场景。每条 chunk 是短事实，不复制完整网页；必须含可验证 URL、locator、fact type 和 expected status。

**Step 4: 实现消融 runner**

```powershell
python -m evals.runner --suite retrieval --mode lexical --offline --report evals/reports/generated/lexical.json
python -m evals.runner --suite retrieval --mode dense --offline --report evals/reports/generated/dense.json
python -m evals.runner --suite retrieval --mode hybrid --offline --report evals/reports/generated/hybrid.json
python -m evals.runner --suite versioning --offline --report evals/reports/generated/versioning.json
```

offline profile 使用 deterministic embedder，不把其数值描述为真实语义模型效果。另提供：

```powershell
python -m evals.runner --suite retrieval --mode hybrid --profile real-embedding --report evals/reports/generated/hybrid-real.json
```

**Step 5: 运行 Eval gates**

Expected：metadata filter accuracy 1.0、expired/superseded leakage 0、provenance completeness 1.0。Recall/MRR/nDCG 在 fixture 完成后写入 baseline，不伪造结果。

**Step 6: Commit**

```powershell
git add apps/agent-python/evals apps/agent-python/tests/evals
git commit -m "test: add hybrid retrieval eval suite"
```

## Task 8：Ingress、Context、Understand、Route 与 RetrievalPlan 状态

**Files:**

- Modify: `apps/agent-python/app/orchestration/state_contracts.py`
- Modify: `apps/agent-python/app/orchestration/transition_table.py`
- Create: `apps/agent-python/app/orchestration/states/ingress.py`
- Create: `apps/agent-python/app/orchestration/states/context_loading.py`
- Create: `apps/agent-python/app/orchestration/states/routing.py`
- Create: `apps/agent-python/app/orchestration/states/retrieval_planning.py`
- Modify: `apps/agent-python/app/orchestration/states/llm_understanding.py`
- Modify: `apps/agent-python/app/understanding/rule_based_understanding.py`
- Modify: `apps/agent-python/app/context/session_context.py`
- Create: `apps/agent-python/tests/states/test_ingress_context.py`
- Create: `apps/agent-python/tests/states/test_understand_route.py`
- Create: `apps/agent-python/tests/states/test_retrieval_planning.py`
- Create: `apps/agent-python/evals/datasets/state_routing.jsonl`

**Step 1: 更新状态图测试**

删除 `RAG_RETRIEVE`，新增：

```python
RETRIEVAL_PLAN = "retrieval_plan"
HYBRID_RETRIEVE = "hybrid_retrieve"
```

合法主路径必须为：

```text
INGRESS → CONTEXT → UNDERSTAND → ROUTE
→ FACT_QUERY | SUITABILITY | COMPARISON
→ RETRIEVAL_PLAN → HYBRID_RETRIEVE
```

**Step 2: 写失败的状态退出门测试**

- Ingress：空 query safe failure；idempotency key 命中不重复运行。
- Context：session 原样传播；history 故障产生 recovery event。
- Understand：parse → repair once → rule fallback → clarification。
- Route：只允许三个 task；裁剪任务进入 clarification。
- RetrievalPlan：景点 1–2 个、fact type 白名单、comparison 每个景点独立 subtask_id。

**Step 3: 运行并确认失败**

Run: `pytest tests/states/test_ingress_context.py tests/states/test_understand_route.py tests/states/test_retrieval_planning.py -q`

**Step 4: 实现 handlers**

复用现有 understanding 组件，但 handler 不得自行循环或吞异常。模型 repair 只允许一次；之后由 rule parser 或 clarification 接管。RetrievalPlan 完全确定性，不调用 LLM。

**Step 5: 运行测试与 routing eval**

Run:

```powershell
pytest tests/states/test_ingress_context.py tests/states/test_understand_route.py tests/states/test_retrieval_planning.py -q
python -m evals.runner --suite state_routing --offline --report evals/reports/generated/state-routing.json
```

Expected: path accuracy ≥ .95、illegal transitions 0。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/orchestration apps/agent-python/app/understanding apps/agent-python/app/context apps/agent-python/tests/states apps/agent-python/evals/datasets/state_routing.jsonl
git commit -m "feat: add retrieval planning state path"
```

## Task 9：Hybrid Retrieve、Evidence Evaluate 与受控 Gap Fill 状态

**Files:**

- Create: `apps/agent-python/app/orchestration/states/hybrid_retrieval.py`
- Create: `apps/agent-python/app/orchestration/states/evidence_evaluation.py`
- Create: `apps/agent-python/app/orchestration/states/live_gap_fill.py`
- Create: `apps/agent-python/app/evidence/claim_decision.py`
- Modify: `apps/agent-python/app/evidence/conflict_resolver.py`
- Modify: `apps/agent-python/app/evidence/coverage_checker.py`
- Create: `apps/agent-python/tests/fakes/failing_retrievers.py`
- Create: `apps/agent-python/tests/states/test_hybrid_retrieval.py`
- Create: `apps/agent-python/tests/states/test_evidence_evaluation.py`
- Create: `apps/agent-python/tests/states/test_live_gap_fill.py`
- Create: `apps/agent-python/evals/datasets/evidence_conflict.jsonl`
- Create: `apps/agent-python/evals/datasets/failure_recovery.jsonl`

**Step 1: 写状态测试**

```python
@pytest.mark.asyncio
async def test_dense_timeout_is_recovered_inside_hybrid_state():
    handler = HybridRetrievalHandler(retriever=lexical_success_dense_timeout())
    result = await handler.run(context_with_plan())
    assert result.status == "recovered"
    assert result.next_state is AgentState.EVIDENCE_EVALUATE
    assert result.recovery.strategy == "lexical_only"
```

覆盖 timeout_once、always_empty、embedding_error、stale_point、conflicting_sources、两路失败、gap fill 429 then success、malformed payload。

**Step 2: 运行并确认失败**

Run: `pytest tests/states/test_hybrid_retrieval.py tests/states/test_evidence_evaluation.py tests/states/test_live_gap_fill.py -q`

**Step 3: 实现三个 handlers**

- Hybrid Retrieve 始终输出 RetrievalReport。
- Evidence Evaluate 始终输出 `ClaimDecision[] + CoverageReport`。
- 冲突双方保留并带 decision reason。
- 一个 run 最多一个 logical gap task、最多两个 execution attempts。
- live 结果只进入 transient Evidence；可选维护写 pending，不直接更新 Qdrant active index。

**Step 4: 比较任务隔离**

每个景点单独执行 plan/retrieve/evaluate，artifact key 使用 `comparison:{subtask_id}`；只将双方共同 fact dimensions 送入 Compose。

**Step 5: 运行测试和 failure eval**

Expected: recovery fixture pass rate 1.0；attempt/budget 上限无违规；硬事实缺失时 abstain。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/orchestration/states apps/agent-python/app/evidence apps/agent-python/tests/fakes apps/agent-python/tests/states apps/agent-python/evals/datasets
git commit -m "feat: add bounded hybrid retrieval states"
```

## Task 10：AnswerClaim、Compose、Citation Guard 与 Delivery

**Files:**

- Create: `apps/agent-python/app/composition/answer_claim.py`
- Create: `apps/agent-python/app/orchestration/states/citation_guard.py`
- Create: `apps/agent-python/app/orchestration/states/delivery.py`
- Modify: `apps/agent-python/app/composition/final_answer_draft.py`
- Modify: `apps/agent-python/app/composition/answer_composer.py`
- Modify: `apps/agent-python/app/orchestration/states/answer_composition.py`
- Replace: `apps/agent-python/app/evidence/citation_checker.py`
- Modify: `apps/agent-python/app/contracts/response.py`
- Modify: `contracts/schemas/travel_query_response.schema.json`
- Create: `apps/agent-python/tests/states/test_composition.py`
- Create: `apps/agent-python/tests/states/test_citation_guard.py`
- Create: `apps/agent-python/evals/datasets/citation.jsonl`
- Create: `apps/agent-python/evals/graders/citation.py`

**Step 1: 写 claim 级失败测试**

```python
def test_expired_evidence_cannot_support_hard_fact():
    report = CitationChecker().check(
        claims=[hard_claim("每日 09:00 开放", evidence_ids=["e-1"])],
        evidence_index={"e-1": evidence(version_status="expired")},
    )
    assert report.decisions[0].status == "unsupported_removed"
    assert report.unsupported_hard_fact_count == 1
```

覆盖 missing ID、missing URL、hash mismatch、unreported conflict、软建议无需硬引用、全部硬事实删除后 safe failure。

**Step 2: 运行并确认失败**

Run: `pytest tests/states/test_composition.py tests/states/test_citation_guard.py -q`

**Step 3: 实现 AnswerClaim 和 CitationReport**

`AnswerClaim` 包含 `claim_id/text/claim_type/hard_fact/evidence_ids/attraction_id/subtask_id`。CitationChecker 只接受 claims + evidence index，不再接收空 fact sheets 做全文正则匹配。

**Step 4: 实现 Compose 修复与确定性 fallback**

LLM 结构失败 repair once；再次失败按 accepted ClaimDecision 和 Evidence 生成模板。模板也必须经过 Citation Guard。

**Step 5: 运行 citation eval**

Expected: citation precision ≥ .95、unsupported hard facts 0、abstention precision ≥ .90。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/composition apps/agent-python/app/orchestration/states apps/agent-python/app/evidence/citation_checker.py apps/agent-python/app/contracts/response.py apps/agent-python/tests/states apps/agent-python/evals contracts/schemas/travel_query_response.schema.json
git commit -m "feat: enforce claim level citation guard"
```

## Task 11：收敛 Run Store、Inspect 与 Replay

**Files:**

- Replace: `apps/agent-python/app/orchestration/agent_core_models.py`
- Replace: `apps/agent-python/app/orchestration/agent_core_store.py`
- Create: `apps/agent-python/app/orchestration/run_inspector.py`
- Create: `apps/agent-python/app/orchestration/replay.py`
- Create: `apps/agent-python/app/orchestration/run_cli.py`
- Create: `apps/agent-python/tests/test_agent_core_store.py`
- Create: `apps/agent-python/tests/test_replay.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_control_tools.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_job_reconciler.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_pipeline_gate.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_research_plan.py`

**Step 1: 写 store/replay tests**

store 只保留 `run/phase_event/execution_attempt/evidence_record/answer_claim/citation_decision/run_metric`。测试证明 query-id inspect 时间线完整，replay 从 Evidence Evaluate 开始且不调用 embedding/Qdrant/FTS5/tool。

**Step 2: 运行并确认失败**

Run: `pytest tests/test_agent_core_store.py tests/test_replay.py -q`

**Step 3: 实现收敛 store 与 CLI**

```powershell
python -m app.orchestration.run_cli inspect --query-id q-123 --db data/agent_runs.sqlite3
python -m app.orchestration.run_cli replay --query-id q-123 --from-state evidence_evaluate --db data/agent_runs.sqlite3
```

replay 新建 run_id，记录 replay_of_run_id，复用 RetrievalReport/Evidence artifacts。

**Step 4: 删除旧 job/control/research-plan**

先 `rg` 确认引用迁移。禁止保留 `except Exception: return` 的审计写入。

**Step 5: 运行测试并提交**

```powershell
pytest tests/test_agent_core_store.py tests/test_replay.py -q
git add -A apps/agent-python/app/orchestration apps/agent-python/tests/test_agent_core_store.py apps/agent-python/tests/test_replay.py
git commit -m "refactor: reduce run store and add replay"
```

## Task 12：切换到唯一 StateMachine、API 安全与健康检查

**Files:**

- Replace: `apps/agent-python/app/orchestration/state_machine.py`
- Modify: `apps/agent-python/app/orchestration/agent_run_service.py`
- Modify: `apps/agent-python/app/api/app_factory.py`
- Modify: `apps/agent-python/app/api/routes.py`
- Modify: `apps/agent-python/app/api/health.py`
- Modify: `apps/agent-python/app/observability/debug_session.py`
- Modify: `apps/agent-python/app/observability/logging.py`
- Modify: `apps/agent-python/app/config.py`
- Create: `apps/agent-python/tests/integration/test_state_machine_flow.py`
- Create: `apps/agent-python/tests/integration/test_api_flow.py`
- Create: `apps/agent-python/tests/integration/test_multi_turn_flow.py`
- Create: `apps/agent-python/tests/integration/test_health_and_auth.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_supervisor.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_tool_surface.py`
- Delete: `apps/agent-python/app/orchestration/claude_state_runner.py`

**Step 1: 写完整离线链测试**

覆盖 fact、suitability、comparison、multi-turn、Qdrant timeout lexical fallback、两路空结果、debug=false、service key、live/ready health。

**Step 2: 运行并确认失败**

Run: `pytest tests/integration -q`

**Step 3: 替换 state_machine.py**

新文件只装配 handlers 和调用 `StateRuntime.run`：

```python
async def run(
    self,
    query: str,
    user_context: dict | None = None,
    session_id: str | None = None,
    *,
    debug: bool = False,
    trace_id: str | None = None,
) -> TravelQueryResponse: ...
```

不保留 `_dispatch_by_answer_mode/_run_itinerary/_run_crowd_inquiry` 或 RootAgentSupervisor 第二链。

**Step 4: 修复 observability/health/auth**

- debug writer 需 payload.debug 与 settings.debug 同时满足。
- `/health/live` 仅进程状态。
- `/health/ready` 检查 SQLite 与 Qdrant；Qdrant 不可用时明确 `degraded`，是否 ready 由配置决定。
- 配置 service key 时校验 `X-Agent-Service-Key`。
- JSON logs 记录版本、attempt、latency 和 recovery，不记录 prompt/context/key。

**Step 5: 运行 Python 全集**

Run: `pytest -q`

Expected: pass；`rg "RootAgentSupervisor|_dispatch_by_answer_mode|_run_itinerary|_run_crowd_inquiry" app tests` 无运行时命中。

**Step 6: Commit**

```powershell
git add -A apps/agent-python/app apps/agent-python/tests/integration
git commit -m "refactor: route requests through hybrid rag state chain"
```

## Task 13：Java-Python 强类型契约与 Trace 传播

**Files:**

- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryCommand.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryResult.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/config/AgentProperties.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java`
- Modify: `apps/api-java/src/main/resources/application.yml`
- Modify: `apps/api-java/src/test/resources/application.yml`
- Create: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClientTest.java`
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/web/TravelProxyControllerTest.java`
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/web/TravelPlatformControllerTest.java`
- Modify: `contracts/schemas/travel_query_request.schema.json`
- Modify: `contracts/schemas/travel_query_response.schema.json`

**Step 1: 写失败的 client tests**

用 `MockRestServiceServer` 验证 session/debug body、`X-Trace-Id`、`X-Agent-Service-Key`、RetrievalReport/Citation/metrics 顶层映射和 timeout/401/5xx 错误码。

**Step 2: 运行并确认失败**

Run: `cd apps/api-java; mvn -Dtest=PythonAgentClientTest,TravelProxyControllerTest,TravelPlatformControllerTest test`

**Step 3: 实现并运行全集**

Run: `mvn test`

Expected: all Java tests pass；conversation id 与 Python session id 一致。

**Step 4: Commit**

```powershell
git add apps/api-java contracts/schemas
git commit -m "feat: harden java rag boundary"
```

## Task 14：Web Evidence、检索降级与状态审计展示

**Files:**

- Create: `apps/web/src/presentation/agent-result.js`
- Create: `apps/web/tests/agent-result.test.js`
- Modify: `apps/web/src/main.js`
- Modify: `apps/web/src/api/types.js`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/package.json`

**Step 1: 写 Node 内置测试**

测试 Evidence source/version/retrieval channels、Citation decision、lexical-only/degraded badge、状态审计 timeline 和旧响应兼容。

**Step 2: 运行并确认失败**

Run: `cd apps/web; node --test tests/agent-result.test.js`

**Step 3: 提取纯展示模型**

`main.js` 不再直接 JSON dump 全部对象；只显示可读 Evidence、Citation、Retrieval 和 State Audit，不显示 raw artifacts。

**Step 4: 验证并提交**

```powershell
npm test
npm run build
git add apps/web
git commit -m "feat: present rag evidence and recovery"
```

## Task 15：物理裁剪超出范围的能力

**Files:**

- Delete: `apps/agent-python/app/composition/itinerary.py`
- Delete: `apps/agent-python/app/composition/nearby_guided_composition.py`
- Delete: `apps/agent-python/app/composition/prompt_templates/composer_itinerary.md`
- Delete: `apps/agent-python/app/composition/prompt_templates/composer_nearby_guided.md`
- Delete: `apps/agent-python/app/evidence/data/baidu_nearby_taxonomy.json`
- Delete: `apps/agent-python/app/evidence/nearby_category_registry.py`
- Delete: `apps/agent-python/app/evidence/nearby_enrichment_policy.py`
- Delete: `apps/agent-python/app/evidence/nearby_recommendation_policy.py`
- Delete: `apps/agent-python/app/evidence/poi_anchor_extraction.py`
- Delete: `apps/agent-python/app/evidence/review.py`
- Delete: `apps/agent-python/app/evidence/review_aspect_normalizer.py`
- Delete: `apps/agent-python/app/evidence/review_llm_extractor.py`
- Delete: `apps/agent-python/app/evidence/review_mining_agent.py`
- Delete: `apps/agent-python/app/evidence/review_persona_generator.py`
- Delete: `apps/agent-python/app/evidence/review_rule_extractor.py`
- Delete: `apps/agent-python/app/evidence/review_signal.py`
- Delete: `apps/agent-python/app/evidence/ticket_area_policy.py`
- Delete: `apps/agent-python/app/evidence/ticket_info.py`
- Delete: `apps/agent-python/app/evidence/ticket_price_audit.py`
- Delete: `apps/agent-python/app/evidence/ticket_price_extractor.py`
- Delete: `apps/agent-python/app/evidence/ticket_relevance_policy.py`
- Delete: `apps/agent-python/app/execution/nearby_enrichment_runner.py`
- Delete: `apps/agent-python/app/execution/nearby_retrieval_runner.py`
- Delete: `apps/agent-python/app/execution/ticket_lookup_attempt_tracker.py`
- Delete: `apps/agent-python/app/planning/nearby_anchor_policy.py`
- Delete: `apps/agent-python/app/planning/nearby_anchor_strategy.py`
- Delete: `apps/agent-python/app/planning/nearby_task_orchestration.py`
- Delete: `apps/agent-python/app/planning/ticket_lookup_helpers.py`
- Delete: `apps/agent-python/app/planning/ticket_lookup_policy.py`
- Delete: `apps/agent-python/app/planning/ticket_price_query_ladder.py`
- Delete: `apps/agent-python/app/planning/ticket_product_policy.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/poi_recommendation.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/review_first.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/route_first.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/ticket_price_lookup.py`
- Delete: `apps/agent-python/app/tools/review_tool.py`
- Delete: `apps/agent-python/tests/test_non_lookup_task_layers.py`
- Delete: `apps/agent-python/tests/test_poi_anchor_extraction.py`
- Delete: `apps/agent-python/tests/test_ticket_lookup_migration.py`
- Modify: `apps/agent-python/app/config.py`
- Modify: `apps/agent-python/app/planning/s5_task_tool_catalogs/resolver.py`
- Modify: `apps/agent-python/app/planning/s5_task_tool_catalogs/shared.py`
- Modify: `apps/agent-python/app/planning/s5_information_domain.py`
- Modify: `apps/agent-python/app/planning/s5_information_domain_registry.py`
- Modify: `apps/agent-python/app/tools/registry.py`
- Modify: `apps/agent-python/tests/characterization/test_supported_scope.py`

**Step 1: 将 scope test 改为硬 gate**

扫描 `app/` import、注册表、intent route 和配置；禁止 itinerary/nearby/crowd/review-crawler/ticket-crawler/neo4j/graph-rag 运行标记。`ticket_price` 作为 RAG fact type 保留。

**Step 2: 确认失败后逐组删除**

Run: `cd apps/agent-python; pytest tests/characterization/test_supported_scope.py -q`

每组删除后运行：

```powershell
python -m compileall -q app
pytest tests/test_layer_consolidation_imports.py tests/characterization/test_supported_scope.py -q
```

适合度只依赖 accessibility/visitor_notice/general_description Evidence，不依赖 review mining。

**Step 3: 全量验证与规模对比**

```powershell
pytest -q
python -m evals.baseline --output evals/reports/generated/after-pruning.json
```

Expected: pass；生产文件和行数低于 Task 1 baseline；无被裁剪运行时引用。

**Step 4: Commit**

```powershell
git add -A apps/agent-python
git commit -m "refactor: remove unsupported travel capabilities"
```

## Task 16：CI、最终 Eval、文档与项目交付

**Files:**

- Create: `.github/workflows/verify.yml`
- Create: `apps/agent-python/evals/datasets/multi_turn.jsonl`
- Create: `apps/agent-python/evals/datasets/comparison.jsonl`
- Create: `apps/agent-python/evals/graders/state_path.py`
- Create: `apps/agent-python/evals/graders/evidence.py`
- Create: `apps/agent-python/evals/graders/operations.py`
- Create: `apps/agent-python/evals/reports/final-offline.json`
- Create: `apps/agent-python/evals/reports/final-offline.md`
- Create: `docs/architecture/STATE_CHAIN.md`
- Create: `docs/architecture/KNOWLEDGE_LIFECYCLE.md`
- Create: `docs/architecture/HYBRID_RETRIEVAL.md`
- Create: `docs/architecture/EVALS.md`
- Modify: `README.md`
- Modify: `RUNBOOK.md`
- Modify: `REPO_MAP.md`
- Modify: `PROJECT_MAINLINE.md`
- Modify: `AGENTS.md`

**Step 1: 补齐约 60 条 Eval cases**

分布：Hybrid Retrieval 20、Metadata/Version 10、State Routing 8、Evidence/Conflict 6、Citation 6、Failure Recovery 6、Multi-turn/Comparison 4。

**Step 2: 实现总 gate 与消融报告**

```powershell
cd apps/agent-python
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json
```

硬门槛：

```text
Recall@3 >= .90
MRR >= .85
nDCG@5 >= .90
metadata filter accuracy = 1.0
expired/superseded leakage = 0
state path accuracy >= .95
illegal transitions = 0
stale vector rejection = 1.0
index rebuild consistency = 1.0
unsupported hard facts = 0
citation precision >= .95
abstention precision >= .90
replay consistency = 1.0
```

报告同时列出 lexical-only、dense-only、hybrid、hybrid+rerank。offline fake embedding 的限制必须写在报告中。

**Step 3: 配置 CI**

四个 job：Python unit+offline eval、Qdrant service integration、Java tests、Web tests+build。Qdrant service 使用 `qdrant/qdrant:v1.19.0` 并设置测试 API key；CI 不调用真实 LLM 或下载 embedding model。

**Step 4: 更新文档**

README 首屏只突出状态链、动态知识治理、Hybrid RAG、Evidence/Citation 和真实 Eval。文档必须包含状态错误矩阵、SQLite/Qdrant 一致性、CLI、消融结果、BadCases 和已裁剪能力。

Qdrant Docker 部署必须注明：当前是单机作品集实现，不宣称 HA、备份或生产集群能力。

**Step 5: 全栈最终验证**

```powershell
cd apps/agent-python
pytest -q
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json
cd ../api-java
mvn test
cd ../web
npm test
npm run build
cd ../..
docker compose -f infra/qdrant/compose.yml config
```

Expected: all pass；最终报告达到硬门槛。

**Step 6: 仓库卫生与提交**

```powershell
git status --short
git diff --check
rg --files | rg "(__pycache__|\.pyc$|debug_last_session|/dist/|/target/|knowledge\.sqlite3|qdrant_storage)"
```

Expected: runtime DB、向量数据、模型缓存、debug/build/cache 不进入 Git。

```powershell
git add .github README.md RUNBOOK.md REPO_MAP.md PROJECT_MAINLINE.md AGENTS.md docs/architecture apps/agent-python/evals infra/qdrant
git commit -m "docs: ship evaluated agentic rag platform"
```

## 最终验收清单

- [ ] 只有一套 Agent 状态链。
- [ ] session_id 在 Web → Java → Python → StateContext 全链一致。
- [ ] SQLite 是唯一知识事实源；Qdrant 可完整重建。
- [ ] Embedding model 变化产生新 index generation。
- [ ] 检索包含 lexical、dense、RRF、active post-filter 和 rerank。
- [ ] Qdrant/Embedding/FTS5 每种故障均有独立降级和审计。
- [ ] 每个硬事实沿 Claim → Evidence → Chunk → Version → URL 回溯。
- [ ] comparison 两个景点独立检索、评估和审计。
- [ ] inspect/replay 可用，replay consistency = 1.0。
- [ ] 检索消融和 BadCase 报告包含真实运行数据。
- [ ] Neo4j/GraphRAG 与其他裁剪能力不出现在运行时。
- [ ] Python、Qdrant、Java、Web 和 offline Eval 全部通过。
