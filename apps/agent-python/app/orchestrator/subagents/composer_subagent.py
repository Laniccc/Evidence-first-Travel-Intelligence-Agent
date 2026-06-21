from app.agents.composer_agent import ComposerAgent
from app.schemas.user_query import TravelAgentState


class ComposerSubagent:
    """Sync fallback wrapper for static composition (tests / legacy)."""

    @staticmethod
    def compose(state: TravelAgentState, arguments: dict) -> str:
        mode = arguments.get("compose_mode", "advisory")
        if mode == "advisory":
            return ComposerAgent.compose_advisory(
                arguments.get("target_label", "目的地"),
                state.evidence,
                state,
            )
        if mode == "single":
            return ComposerAgent.compose_single(
                arguments["place_name"],
                arguments["recommendation"],
                arguments["review"],
                arguments["fact_sheet"],
                state,
            )
        if mode == "crowd":
            return ComposerAgent.compose_crowd_inquiry(
                arguments["place_name"],
                arguments["fact_sheet"],
                arguments["review"],
                state,
            )
        if mode == "compare":
            return ComposerAgent.compose_compare(arguments["ranked"], state)
        if mode == "itinerary":
            return ComposerAgent.compose_itinerary(arguments["plan"], state)
        return arguments.get("fallback_text", state.final_response or "")
