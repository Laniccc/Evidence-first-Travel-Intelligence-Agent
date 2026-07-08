from app.schemas.user_query import TravelAgentState


class TraceRecorder:
    @staticmethod
    def add(state: TravelAgentState, message: str) -> None:
        state.visible_trace.append(message)

    @staticmethod
    def add_many(state: TravelAgentState, messages: list[str]) -> None:
        state.visible_trace.extend(messages)
