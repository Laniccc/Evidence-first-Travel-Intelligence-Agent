from app.catalog.place_catalog import get_place_catalog
from app.schemas.conversation_context import ConversationContext
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.place_context import PlaceContext
from app.schemas.user_profile import UserProfile
from app.schemas.user_query import TravelAgentState, UserContext


class ConversationContextBuilder:
    def __init__(self) -> None:
        self.catalog = get_place_catalog()

    def build(
        self,
        state: TravelAgentState,
        user_context: dict | None = None,
        user_ctx: UserContext | None = None,
    ) -> ConversationContext:
        raw_ctx = (user_context or {}).get("conversation_context") or {}
        memory = ConversationMemory.from_user_context(user_context)

        last_places: list[PlaceContext] = []
        if isinstance(raw_ctx, dict) and raw_ctx.get("last_places"):
            for item in raw_ctx["last_places"]:
                if isinstance(item, PlaceContext):
                    last_places.append(item)
                elif isinstance(item, dict):
                    last_places.append(PlaceContext.model_validate(item))
                elif isinstance(item, str):
                    last_places.append(self._place_from_name(item))
        elif memory.last_places:
            last_places = [self._place_from_name(p) for p in memory.last_places]

        profile = None
        if user_ctx and user_ctx.party:
            profile = UserProfile(party=[p.value for p in user_ctx.party], pace=user_ctx.pace.value if user_ctx.pace.value != "unknown" else None)
        elif isinstance(raw_ctx, dict) and raw_ctx.get("last_user_profile"):
            profile = UserProfile.model_validate(raw_ctx["last_user_profile"])

        return ConversationContext(
            last_places=last_places,
            last_city=(raw_ctx.get("last_city") if isinstance(raw_ctx, dict) else None) or memory.last_city,
            last_country=(raw_ctx.get("last_country") if isinstance(raw_ctx, dict) else None) or memory.last_country,
            last_travel_date=(raw_ctx.get("last_travel_date") if isinstance(raw_ctx, dict) else None) or memory.travel_date or (user_ctx.travel_date if user_ctx else None),
            last_user_profile=profile,
            last_itinerary=raw_ctx.get("last_itinerary") if isinstance(raw_ctx, dict) else None,
            last_task_type=raw_ctx.get("last_task_type") if isinstance(raw_ctx, dict) else None,
            confirmed_preferences=raw_ctx.get("confirmed_preferences", []) if isinstance(raw_ctx, dict) else [],
            recent_turns_summary=raw_ctx.get("recent_turns_summary") if isinstance(raw_ctx, dict) else memory.last_query,
        )

    def _place_from_name(self, name: str) -> PlaceContext:
        ctx = self.catalog.resolve_place_context(name)
        return ctx.model_copy(update={"source": "query_understanding"})
