from app.observability.trace import TraceRecorder
from app.orchestration._legacy_boundary import legacy_config_attr
from app.understanding.rewritten_query import RewrittenQueryResult
from app.orchestration.travel_agent_state import TravelAgentState
from app.understanding.user_query import UserContext

get_settings = legacy_config_attr("get_settings")


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
