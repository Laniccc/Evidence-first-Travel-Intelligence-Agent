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
    skills_prompt: str = "",
) -> PhaseToolResult:
    """Decompose a research query into sub-questions and select search sources.

    Uses LLM to:
    1. Understand the research intent
    2. Break down into 2-6 sub-questions
    3. Assign appropriate search sources to each
    """
    sub_questions = await _plan_sub_questions(query, llm_client, skills_prompt=skills_prompt)

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


async def _plan_sub_questions(query: str, llm_client: Any = None, *, skills_prompt: str = "") -> list[ResearchSubQuestion]:
    """Generate sub-questions. Falls back to keyword-based decomposition if no LLM client."""
    if llm_client:
        try:
            return await _llm_decompose(query, llm_client, skills_prompt=skills_prompt)
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


async def _llm_decompose(query: str, llm_client: Any, *, skills_prompt: str = "") -> list[ResearchSubQuestion]:
    """Use LLM to intelligently decompose a research query with multi-angle strategy."""
    import re as _re

    system = "You are a research strategist. Decompose topics into diverse search angles. Target authoritative sources. Output ONLY valid JSON."
    if skills_prompt:
        system = skills_prompt + "\n\n" + system

    prompt = f"""Research topic: {query}

Decompose into 3-6 sub-questions, each targeting a DIFFERENT search angle:
1. Definition / Overview — what is it, key concepts
2. Data / Statistics — numbers, trends, rankings
3. Comparison / Analysis — vs alternatives, pros/cons
4. Latest / Recent — new developments, current state
5. Examples / Case Studies — real-world instances
6. Official / Authoritative — docs, standards, specs

STRATEGY:
- Craft 2-7 word keyword search queries that surface specific, high-quality pages.
- Use site-specific searches when a known platform has the data:
  - GitHub: "site:github.com trending skills" or "site:github.com topics X"
  - Wikipedia: "site:wikipedia.org X"
  - Official docs: "site:docs.python.org X" or "X documentation"
  - Academic: "site:arxiv.org X"
- When the query mentions a specific website or platform, add the DIRECT URL to fetch (e.g. for GitHub trending → "https://github.com/trending").
- Each sub-question may include an optional "direct_urls" list for pages that don't need searching.

Respond as JSON only:
{{"sub_questions": [
  {{"question": "sub-question text",
    "search_query": "targeted keyword search",
    "search_sources": ["general"],
    "expected_claim_types": ["fact"|"statistical_claim"|"analysis"|"summary"],
    "direct_urls": []
  }}
]}}"""

    try:
        text = await llm_client.complete(
            system=system,
            user=prompt,
            max_tokens=2048,
            json_only=True,
        )
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
                direct_urls=q.get("direct_urls", []),
            )
            for q in data.get("sub_questions", [])
        ]
    except Exception as e:
        logger.warning("LLM decomposition failed: %s", e)

    raise ValueError("LLM decomposition failed")
