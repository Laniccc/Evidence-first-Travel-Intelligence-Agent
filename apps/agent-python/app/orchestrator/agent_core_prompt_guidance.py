"""Prompt guidance derived from Agent Core research plans and task classes."""

from __future__ import annotations

from app.schemas.user_query import TravelAgentState


def agent_core_task_guidance(state: TravelAgentState, task_class: str | None = None) -> list[str]:
    task = task_class or _safe_task_class(state)
    rules = [
        "Preserve the ResearchPlan claim_plans: do not switch to another task class unless the input_contract changes.",
        "A tool attempt with no claim-relevant evidence is not sufficient coverage; continue with the next planned source family or finish with an explicit limitation.",
        "Never let unrelated claims hijack the answer: route questions answer route/duration/distance; ticket questions answer explicit prices; geo facts answer numeric geographic facts.",
        "When evidence is partial, preserve the usable claim-relevant facts and label their source class instead of replacing the task with a safer adjacent topic.",
    ]
    if task == "ticket_price_lookup":
        rules.extend(
            [
                "Ticket price evidence is valid only when it contains an explicit amount, price range, or free-entry policy tied to the target place/product.",
                "For China attraction ticket_price, attempt a bounded ticket-platform source early when allowed (for example fliggy_ticket_api_mcp) before repeating generic search.",
                "Platform ticket evidence is candidate evidence unless corroborated by official/operator/government source; still extract the amount and label it as third-party candidate.",
                "Do not mark a ticket task covered when ticket-platform output has product names but no amount.",
                "If official pages require login or block reading, treat that as a source limitation and continue to government/operator snippets or platform candidates; do not claim ticket prices require login.",
                "Do not invent or normalize prices from unrelated products, combo packages, old forum posts, or SEO summaries; bind every amount to its product name and source URL/title.",
            ]
        )
    elif task == "geo_fact_lookup":
        rules.extend(
            [
                "Stable geographic numeric facts such as elevation may use authoritative encyclopedia/geographic sources as partial or strong evidence when official pages are unavailable.",
                "Search queries must include the exact claim word (for example elevation, altitude, main peak, or haiba) and the target place; reject ticket/SEO snippets.",
                "Do not drift to ticket/opening-hours facts for elevation or area questions.",
                "For mountain elevation, accept a direct numeric value from a high-quality encyclopedia/geographic source when two official attempts fail.",
            ]
        )
    elif task == "route_first":
        rules.extend(
            [
                "Route tasks must keep claim_target/information_need in route_plan, duration, distance, transit, or traffic_status.",
                "Every route subtask must carry tool_parameters.origin and tool_parameters.destination; resolve missing endpoints before route tools.",
                "Do not answer opening_hours, ticket_price, weather, or generic place facts unless they directly support route feasibility.",
                "If the user says from A to B, A is origin and B is destination even when entity extraction only returns one place.",
            ]
        )
    elif task == "review_first":
        rules.extend(
            [
                "Review/queue questions should prioritize review_first unless the user explicitly asks current real-time status.",
                "Queue-time questions may use recent review/crowd signals as partial evidence; label them as non-real-time if no live queue source exists.",
                "Do not collapse review sentiment or queue tendency into weather/live_status.",
                "For queue duration or reputation questions, collect review or crowd tendency first; live data is optional corroboration, not the primary task.",
            ]
        )
    elif task == "multi_place_parallel":
        rules.extend(
            [
                "Comparison tasks need balanced per-place evidence; query each named place for the same dimensions before concluding insufficiency.",
                "If evidence is asymmetric, present the usable partial comparison instead of only refusing.",
                "Do not over-trigger disambiguation for obvious China landmark pairs when city/region context is inferable.",
            ]
        )
    elif task == "live_status":
        rules.extend(
            [
                "Live-status answers should separate directly observed live data from forecast/review proxies.",
                "If live traffic/crowd is unavailable, give the best available proxy only when clearly labeled as non-real-time.",
            ]
        )
    elif task == "poi_recommendation":
        rules.extend(
            [
                "Nearby/POI tasks should answer the requested POI category first and avoid adding unrelated sections.",
                "If candidates are found, do not conclude 'no usable evidence' merely because cross-source corroboration is absent; label them as map candidates.",
            ]
        )
    return rules


def agent_core_task_guidance_block(state: TravelAgentState, task_class: str | None = None) -> str:
    rules = agent_core_task_guidance(state, task_class=task_class)
    return "## Agent Core task guardrails\n" + "\n".join(f"- {rule}" for rule in rules)


def _safe_task_class(state: TravelAgentState) -> str | None:
    try:
        from app.orchestrator.agent_tool_catalog import resolve_s5_task_class

        return resolve_s5_task_class(state)
    except Exception:
        return None
