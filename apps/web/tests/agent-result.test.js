import test from "node:test";
import assert from "node:assert/strict";

import { buildAgentResultView } from "../src/presentation/agent-result.js";

test("publication snapshot distinguishes review, rejection, pending index and indexed", () => {
  for (const [status, index, label] of [
    ["rejected", "not_applicable", "候选已拒绝"],
    ["pending_review", "not_applicable", "待人工审核"],
    ["published", "pending", "已发布，索引待同步"],
    ["published", "indexed", "已发布，已索引"],
  ]) {
    const view = buildAgentResultView({promotion_summary: {status, raw_payload: "private-location-secret"},
      index_sync_status: {status: index, api_key: "private-key"}});
    assert.equal(view.knowledge.label, label);
    assert.equal(JSON.stringify(view).includes("private-"), false);
  }
  assert.equal(buildAgentResultView({answer: "legacy"}).knowledge, null);
  const unknown = buildAgentResultView({promotion_summary: {status: "private-secret"}, index_sync_status: {status: "private-key"}});
  assert.equal(unknown.knowledge.label, "知识维护状态未知");
  assert.equal(JSON.stringify(unknown).includes("private-"), false);
});

test("builds readable evidence provenance and retrieval channels", () => {
  const view = buildAgentResultView({
    answer: "八点半开放",
    evidence_summary: [
      {
        evidence_id: "e-1",
        content: "故宫八点半开放",
        source_title: "故宫官网",
        source_url: "https://example.test/official",
        document_version_id: "v-2",
        corpus_version: "corpus-1",
        fact_type: "opening_hours",
      },
    ],
    retrieval_reports: [
      {
        subtask_id: "sub-1",
        degradation: "lexical_only",
        corpus_version: "corpus-1",
        lexical_attempt: { channel: "lexical", status: "success", result_count: 1 },
        dense_attempt: { channel: "dense", status: "failed", failure_code: "timeout" },
      },
    ],
  });

  assert.equal(view.evidence[0].sourceLabel, "故宫官网");
  assert.equal(view.evidence[0].versionLabel, "v-2 · corpus-1");
  assert.deepEqual(view.retrieval[0].channels, ["lexical: success (1)", "dense: failed · timeout"]);
  assert.equal(view.retrieval[0].badge, "Lexical fallback");
  assert.equal(view.degraded, true);
});

test("projects citation decisions and safe state audit without raw artifacts", () => {
  const view = buildAgentResultView({
    citation_report: {
      citation_precision: 1,
      decisions: [
        { claim_id: "c-1", status: "supported", reason: "claim_evidence_chain_valid", evidence_ids: ["e-1"] },
      ],
    },
    orchestration_summary: {
      terminal_state: "deliver",
      state_audit: [
        {
          event_type: "phase_recovered",
          state: "hybrid_retrieve",
          attempt: 1,
          duration_ms: 12.5,
          recovery: { strategy: "lexical_only" },
          output: { secret_raw_artifact: true },
          input_digest: "digest",
        },
      ],
    },
  });

  assert.deepEqual(view.citations[0], {
    claimId: "c-1",
    status: "supported",
    reason: "claim_evidence_chain_valid",
    evidenceIds: ["e-1"],
  });
  assert.deepEqual(view.timeline[0], {
    state: "hybrid_retrieve",
    status: "recovered",
    attempt: 1,
    latency: "12.5 ms",
    recovery: "lexical_only",
    failureCode: null,
  });
  assert.equal(JSON.stringify(view).includes("secret_raw_artifact"), false);
  assert.equal(JSON.stringify(view).includes("input_digest"), false);
});

test("keeps legacy responses readable", () => {
  const view = buildAgentResultView({
    answer: "legacy answer",
    confidence: 0.8,
    visible_trace: ["understood", "planned"],
    evidence_summary: [{ source_url: "https://example.test/legacy" }],
    citation_check_result: { passed: true },
  });

  assert.equal(view.answer, "legacy answer");
  assert.equal(view.confidenceLabel, "80%");
  assert.equal(view.evidence[0].sourceLabel, "example.test");
  assert.deepEqual(view.timeline.map((item) => item.state), ["understood", "planned"]);
  assert.equal(view.citationSummary, "Citation check passed");
});
