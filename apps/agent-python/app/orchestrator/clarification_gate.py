from app.config import get_settings
from app.orchestrator.trace import TraceRecorder
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.user_query import TravelAgentState, UserContext


class ClarificationGate:
    @staticmethod
    def apply(state: TravelAgentState) -> bool:
        """Return True if pipeline should stop for clarification."""
        qu = state.query_understanding
        if not qu or not qu.needs_clarification:
            return False

        state.next_state = "clarification_response"
        state.final_response = qu.clarification_question or "请补充您想查询的具体景点或区域。"
        state.limitations.extend(qu.missing_critical_info)
        state.limitations.append("用户问题存在无法解析的指代，需要澄清。")
        state.structured_result = {
            "status": "needs_clarification",
            "recommendation": None,
            "places": [],
        }
        TraceRecorder.add(state, "✓ 用户问题存在无法解析的指代，已暂停工具调用")
        return True
