"""Run a small China-only task-class matrix against the live agent.

This is an operator helper, not a pytest suite: it calls real LLM/MCP tools and
writes a compact JSON report for manual analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from app.orchestrator.state_machine import TravelAgentStateMachine


TASK_CLASS_MATRIX: list[dict[str, str]] = [
    {"task_class": "poi_recommendation", "query": "\u5317\u4eac\u6545\u5bab\u9644\u8fd1\u6709\u4ec0\u4e48\u597d\u5403\u7684\uff1f"},
    {"task_class": "poi_recommendation", "query": "\u676d\u5dde\u897f\u6e56\u9644\u8fd1\u6709\u6ca1\u6709\u516c\u5171\u5395\u6240\uff1f"},
    {"task_class": "strict_fact_lookup", "query": "\u6545\u5bab\u535a\u7269\u9662\u5f00\u653e\u65f6\u95f4\uff1f"},
    {"task_class": "strict_fact_lookup", "query": "\u725b\u9996\u5c71\u6587\u5316\u65c5\u6e38\u533a\u9700\u8981\u9884\u7ea6\u5417\uff1f"},
    {"task_class": "ticket_price_lookup", "query": "\u6816\u971e\u5c71\u95e8\u7968\u4ef7\u683c\u591a\u5c11\uff1f"},
    {"task_class": "ticket_price_lookup", "query": "\u5175\u9a6c\u4fd1\u95e8\u7968\u591a\u5c11\u94b1\uff1f"},
    {"task_class": "geo_fact_lookup", "query": "\u9ec4\u5c71\u4e3b\u5cf0\u6d77\u62d4\u591a\u5c11\u7c73\uff1f"},
    {"task_class": "geo_fact_lookup", "query": "\u6cf0\u5c71\u6d77\u62d4\u591a\u5c11\u7c73\uff1f"},
    {"task_class": "live_status", "query": "\u5317\u4eac\u4eca\u5929\u5929\u6c14\u9002\u5408\u901b\u6545\u5bab\u5417\uff1f"},
    {"task_class": "live_status", "query": "\u73b0\u5728\u53bb\u516b\u8fbe\u5cad\u957f\u57ce\u8def\u4e0a\u5835\u5417\uff1f"},
    {"task_class": "multi_place_parallel", "query": "\u6545\u5bab\u548c\u9890\u548c\u56ed\u54ea\u4e2a\u66f4\u9002\u5408\u5e26\u8001\u4eba\uff1f"},
    {"task_class": "multi_place_parallel", "query": "\u9ec4\u5c71\u548c\u6cf0\u5c71\u54ea\u4e2a\u66f4\u9002\u5408\u7b2c\u4e00\u6b21\u722c\u5c71\uff1f"},
    {"task_class": "route_first", "query": "\u4ece\u5317\u4eac\u5357\u7ad9\u5230\u5929\u5b89\u95e8\u5e7f\u573a\u5750\u5730\u94c1\u600e\u4e48\u8d70\uff1f"},
    {"task_class": "route_first", "query": "\u4ece\u676d\u5dde\u4e1c\u7ad9\u5230\u897f\u6e56\u6253\u8f66\u5927\u6982\u591a\u4e45\uff1f"},
    {"task_class": "review_first", "query": "\u5357\u4eac\u5927\u724c\u6863\u53e3\u7891\u600e\u4e48\u6837\uff1f"},
    {"task_class": "review_first", "query": "\u5e7f\u5dde\u957f\u9686\u91ce\u751f\u52a8\u7269\u4e16\u754c\u6392\u961f\u4e45\u4e0d\u4e45\uff1f"},
    {"task_class": "mixed_advisory", "query": "\u51e0\u6708\u53bb\u676d\u5dde\u897f\u6e56\u6700\u5408\u9002\uff1f"},
    {"task_class": "mixed_advisory", "query": "\u51ac\u5929\u53bb\u54c8\u5c14\u6ee8\u65c5\u6e38\u9700\u8981\u6ce8\u610f\u4ec0\u4e48\uff1f"},
    {"task_class": "minimal_probe", "query": "\u53bb\u957f\u57ce\u73a9\u600e\u4e48\u5b89\u6392\uff1f"},
    {"task_class": "minimal_probe", "query": "\u6811\u4eba\u4e2d\u5b66\u9644\u8fd1\u6709\u4ec0\u4e48\uff1f"},
]


def _compact_response(row: dict[str, str], response: Any, elapsed_s: float) -> dict[str, Any]:
    orchestration = response.orchestration_summary or {}
    limitations = response.limitations or []
    traces = response.visible_trace or []
    tool_traces = response.tool_traces or []
    return {
        **row,
        "elapsed_s": round(elapsed_s, 2),
        "answer": response.answer,
        "confidence": response.confidence,
        "answer_mode": response.answer_mode,
        "resolved_task_class": orchestration.get("s5_task_class"),
        "evidence_count": len(response.evidence_summary or []),
        "limitations": limitations,
        "limitations_count": len(limitations),
        "trace_count": len(traces),
        "tool_count": len(tool_traces),
        "tool_rollup": _tool_rollup(tool_traces),
        "semantic_frame": response.semantic_frame_summary,
        "orchestration_summary": orchestration,
    }


def _tool_rollup(tool_traces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trace in tool_traces:
        name = str(trace.get("tool_name") or trace.get("tool") or "unknown")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


async def _run_one(row: dict[str, str], timeout_s: float) -> dict[str, Any]:
    start = time.perf_counter()
    sm = TravelAgentStateMachine()
    try:
        response = await asyncio.wait_for(sm.run(row["query"], {}), timeout=timeout_s)
    except Exception as exc:  # Keep the batch going so the report shows partial failures.
        return {
            **row,
            "elapsed_s": round(time.perf_counter() - start, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return _compact_response(row, response, time.perf_counter() - start)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N rows.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-query timeout in seconds.")
    parser.add_argument(
        "--output",
        default="debug_task_class_eval_results.json",
        help="Output JSON path, relative to apps/agent-python unless absolute.",
    )
    args = parser.parse_args()

    rows = TASK_CLASS_MATRIX[: args.limit] if args.limit else TASK_CLASS_MATRIX
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        print(f"[{index}/{len(rows)}] {row['task_class']}: {row['query']}", flush=True)
        result = await _run_one(row, timeout_s=args.timeout)
        results.append(result)
        status = "ERROR" if "error" in result else f"ok evidence={result.get('evidence_count')}"
        print(f"  -> {status} elapsed={result.get('elapsed_s')}s", flush=True)

    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parents[2] / output
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
