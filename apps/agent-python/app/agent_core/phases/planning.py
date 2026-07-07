"""Phase 1: Research Planning — decompose query into sub-questions and search strategy."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import (
    PhaseToolResult,
    ResearchPlanArtifact,
    ResearchSubQuestion,
)

logger = logging.getLogger(__name__)


async def run_planning(  # noqa: RUF029 — async for supervisor consistency
    store,
    run_id: str,
    query: str,
    llm_client: Any = None,
) -> PhaseToolResult:
    """Decompose a research query into sub-questions and select search sources.

    Uses LLM to:
    1. Understand the research intent
    2. Break down into 2-6 sub-questions
    3. Assign appropriate search sources to each
    """
    sub_questions = await _plan_sub_questions(query, llm_client)

    plan = ResearchPlanArtifact(
        topic_title=query[:80],
        sub_questions=sub_questions,
        search_strategy="balanced",
    )

    artifact = await complete_phase_with_artifact(
        store,
        phase_name="planning",
        artifact_type="research_plan",
        payload=plan.model_dump(),
    )

    # Create a topic for each sub-question
    for sq in sub_questions:
        store.create_topic(
            task_class="general_research",
            user_question=sq.question,
            normalized_claim=sq.search_query,
        )

    return PhaseToolResult(
        artifacts=[artifact],
        events=[],
    )


async def _plan_sub_questions(query: str, llm_client: Any = None) -> list[ResearchSubQuestion]:
    """Generate sub-questions. Falls back to keyword-based decomposition if no LLM client."""
    if llm_client:
        try:
            return await _llm_decompose(query, llm_client)
        except Exception:
            logger.warning("LLM decomposition failed, falling back to keyword-based")

    # Fallback: simple decomposition
    return [
        ResearchSubQuestion(
            question=f"Overview of {query}",
            search_query=query,
            search_sources=["general"],
            expected_claim_types=["summary"],
        ),
        ResearchSubQuestion(
            question=f"Key details about {query}",
            search_query=f"{query} details analysis",
            search_sources=["general", "news"],
            expected_claim_types=["fact", "data"],
        ),
    ]


async def _llm_decompose(query: str, llm_client: Any) -> list[ResearchSubQuestion]:
    """Use LLM to intelligently decompose a research query."""
    import re as _re

    prompt = f"""Research topic: {query}

Decompose this into 2-5 specific sub-questions. For each, suggest a search query.
Respond as JSON only:
{{"sub_questions": [{{"question": "...", "search_query": "...", "search_sources": ["general"]}}]}}"""

    try:
        text = await llm_client.complete(
            system="You are a research planner. Decompose topics into sub-questions. Output ONLY valid JSON.",
            user=prompt,
            max_tokens=2048,
            json_only=True,
        )
        # Try parsing as-is first
        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            match = _re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("No JSON found in LLM response")
        return [
            ResearchSubQuestion(
                question=q["question"],
                search_query=q.get("search_query", q["question"]),
                search_sources=q.get("search_sources", ["general"]),
                expected_claim_types=q.get("expected_claim_types", ["fact"]),
            )
            for q in data.get("sub_questions", [])
        ]
    except Exception as e:
        logger.warning("LLM decomposition failed: %s", e)

    raise ValueError("LLM decomposition failed")
