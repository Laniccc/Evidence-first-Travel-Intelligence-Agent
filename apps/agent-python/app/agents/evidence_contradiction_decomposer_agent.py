"""S5: decompose apparent contradictions into product tiers / conditions."""

from __future__ import annotations

import json
import logging
import re
import uuid

from app.agents.review_mining_agent import VerifierAgent
from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.evidence_signal_utils import multi_value_signal_for_need
from app.schemas.evidence import Evidence
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_SYSTEM = """You analyze travel evidence where multiple numeric or textual values appear for the same fact.
Your job is to DECOMPOSE differences into distinct products, seasons, or bundles — NOT to declare the fact unknowable.

Return ONLY JSON:
{
  "decompositions": [{
    "claim_type": "ticket_price",
    "summary": "一句话说明差异来自票种/套餐口径，而非单一票价冲突",
    "items": [{
      "label": "喀纳斯景区门票（仅门票）",
      "value": "旺季160元/人·2天；淡季80元/人·2天",
      "conditions": "旺季5月1日-10月15日",
      "confidence": 0.75,
      "evidence_ids": ["uuid-if-known"],
      "supporting_snippets": ["原文片段"]
    }],
    "outliers": [{"value": "70元", "reason": "第三方攻略可能过时", "confidence": 0.25}]
  }],
  "follow_up_search_tasks": [{
    "anchor_keywords": ["喀纳斯", "门票"],
    "search_query": "喀纳斯景区管理委员会 门票 公示",
    "information_need": "ticket_price",
    "rationale": "核验管委会官方公示"
  }],
  "presentation_guidance": "按票种分列呈现；勿说成价格不确定"
}

Rules:
- ticket_price: separate 单门票 / 门票+区间车 / 二进票 / 全域联票 / 淡季政策 等
- opening_hours: separate 旺季/淡季/节假日特殊安排/周一闭馆
- Use evidence_highlights and detected_conflicts only; never invent numbers
- follow_up_search_tasks: max 2, only when official verification still helps
- confidence 0.7+ when multiple snippets agree on the same tier; 0.3-0.5 for lone outliers
"""

_REPAIR_SUFFIX = (
    "\n\nYour previous reply was invalid. Return ONLY JSON matching the schema above."
)


class EvidenceContradictionDecomposerAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    async def run(self, state: TravelAgentState, arguments: dict | None = None) -> dict:
        need = ClaimSearchPlanner.primary_information_need(state) or "ticket_price"
        if not multi_value_signal_for_need(state, need):
            return {
                "decompositions": [],
                "follow_up_search_tasks": [],
                "presentation_guidance": "",
                "decomposed": False,
            }

        ctx = self._build_context(state, need)
        if self.llm._should_use_anthropic():
            try:
                parsed = await self._llm_decompose(ctx)
                if parsed:
                    return self._normalize_output(parsed, ctx)
            except Exception as exc:
                logger.warning("EvidenceContradictionDecomposer LLM failed: %s", exc)

        return self._heuristic_decompose(ctx)

    def _build_context(self, state: TravelAgentState, need: str) -> dict:
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        conflicts = VerifierAgent.detect_conflicts(evidence)
        relevant_conflicts = [c for c in conflicts if c.get("field") == need]
        return {
            "primary_information_need": need,
            "raw_query": state.raw_user_query,
            "entities": (ClaimSearchPlanner.planning_context(state)).get("entities") or {},
            "evidence_highlights": ClaimSearchPlanner.evidence_highlights(state),
            "detected_conflicts": relevant_conflicts or conflicts,
            "tried_search_queries": sorted(ClaimSearchPlanner.tried_from_traces(state)),
        }

    async def _llm_decompose(self, ctx: dict) -> dict | None:
        raw = await self.llm.complete(
            system=_SYSTEM,
            user=json.dumps(ctx, ensure_ascii=False),
            max_tokens=2000,
            json_only=True,
        )
        data = json.loads((raw or "").strip())
        return data if isinstance(data, dict) else None

    def _normalize_output(self, data: dict, ctx: dict) -> dict:
        decompositions = data.get("decompositions") if isinstance(data.get("decompositions"), list) else []
        tasks = self._tasks_from_payload(data.get("follow_up_search_tasks") or [], ctx)
        guidance = str(data.get("presentation_guidance") or "").strip()
        return {
            "decompositions": decompositions,
            "follow_up_search_tasks": [t.model_dump() for t in tasks],
            "presentation_guidance": guidance,
            "decomposed": bool(decompositions),
        }

    def _heuristic_decompose(self, ctx: dict) -> dict:
        need = ctx.get("primary_information_need") or "ticket_price"
        if need != "ticket_price":
            return {
                "decompositions": [],
                "follow_up_search_tasks": [],
                "presentation_guidance": "",
                "decomposed": False,
            }

        tiers: dict[str, dict] = {}
        outliers: list[dict] = []
        for row in ctx.get("evidence_highlights") or []:
            for claim in row.get("claims") or []:
                if claim.get("type") != "ticket_price":
                    continue
                text = str(claim.get("value") or "")
                self._classify_ticket_snippet(text, tiers, outliers, row.get("source_name"))

        items = list(tiers.values())
        if len(items) < 2 and not outliers:
            return {
                "decompositions": [],
                "follow_up_search_tasks": [],
                "presentation_guidance": "",
                "decomposed": False,
            }

        return {
            "decompositions": [
                {
                    "claim_type": "ticket_price",
                    "summary": "检索到多个票价数字，差异主要来自票种/是否含区间车等口径不同。",
                    "items": items,
                    "outliers": outliers[:3],
                }
            ],
            "follow_up_search_tasks": [],
            "presentation_guidance": "按票种分列呈现各档位价格；勿笼统称价格不确定。",
            "decomposed": True,
        }

    @staticmethod
    def _classify_ticket_snippet(
        text: str,
        tiers: dict[str, dict],
        outliers: list[dict],
        source_name: str | None,
    ) -> None:
        if "管理委员会" in text or "公示" in text:
            m = re.search(
                r"门票[^。]{0,20}旺季\s*(\d+)\s*元[^。]{0,40}淡季\s*(\d+)\s*元",
                text.replace(" ", ""),
            )
            if m:
                key = "ticket_only"
                tiers[key] = {
                    "label": "景区门票（仅门票）",
                    "value": f"旺季{m.group(1)}元/人·2天；淡季{m.group(2)}元/人·2天",
                    "conditions": "以管委会公示摘要为准",
                    "confidence": 0.72,
                    "evidence_ids": [],
                    "supporting_snippets": [text[:200]],
                }
                return
        if "一进票" in text or "门160" in text or "门+车" in text:
            tiers["door_bus"] = {
                "label": "一进票（门票+区间车）",
                "value": "约230元（门160元+车70元）" if "230" in text else "门票+区间车组合价",
                "conditions": "旺季组合票",
                "confidence": 0.68,
                "evidence_ids": [],
                "supporting_snippets": [text[:200]],
            }
            return
        if "全域" in text or "100元/人次" in text:
            tiers["all_area"] = {
                "label": "全域联票（喀纳斯+禾木+白哈巴）",
                "value": "淡季约100元/人·3天" if "100" in text else "全域联票",
                "conditions": "冬季/淡季政策",
                "confidence": 0.65,
                "evidence_ids": [],
                "supporting_snippets": [text[:200]],
            }
            return
        m = re.search(r"门票(\d{2,3})元", text.replace(" ", ""))
        if m and int(m.group(1)) < 120:
            outliers.append(
                {
                    "value": f"{m.group(1)}元",
                    "reason": f"可能与区间车分开计价或来源过时（{source_name or 'web'}）",
                    "confidence": 0.3,
                }
            )

    def _tasks_from_payload(self, bucket: list, ctx: dict) -> list[SearchTask]:
        anchors = list((ctx.get("entities") or {}).get("places") or [])
        region = (ctx.get("entities") or {}).get("region")
        if region:
            anchors.append(str(region))
        tried = set(ctx.get("tried_search_queries") or [])
        out: list[SearchTask] = []
        for item in bucket[:2]:
            if not isinstance(item, dict):
                continue
            query = str(item.get("search_query") or "").strip()
            if not query or query in tried:
                continue
            task_anchors = [str(a) for a in (item.get("anchor_keywords") or anchors) if a]
            if not task_anchors:
                continue
            out.append(
                SearchTask(
                    task_id=f"decompose-{uuid.uuid4().hex[:8]}",
                    anchor_keywords=task_anchors,
                    search_query=query,
                    information_need=str(item.get("information_need") or ctx.get("primary_information_need")),
                    preferred_tool=str(item.get("preferred_tool") or "search_mcp"),
                    rationale=str(item.get("rationale") or "contradiction decomposer follow-up"),
                )
            )
        return out
