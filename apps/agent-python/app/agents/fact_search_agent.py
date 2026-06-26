"""S5 sub-agent: web/official/ticket fact retrieval (wraps keyword_search_agent semantics)."""

from __future__ import annotations

from app.agents.keyword_search_agent import KeywordSearchAgent
from app.agents.s5_subagent_registry import S5_SUBAGENT_PROFILES
from app.schemas.search_task import SearchTask
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

_PROFILE = S5_SUBAGENT_PROFILES["fact_search_agent"]


class FactSearchAgent(KeywordSearchAgent):
    """Fact lookup via diversified MCP rotation — not search_mcp-only."""

    _SUBAGENT_NAME = "fact_search_agent"

    @staticmethod
    def pick_tool(
        task: SearchTask,
        whitelist: ToolWhitelist | None,
        agent_tool_definitions: list[dict] | None = None,
        *,
        state: TravelAgentState | None = None,
    ) -> str:
        usable = FactSearchAgent._preferred_tool_is_usable(task, whitelist)
        if usable:
            return usable

        for tool in _PROFILE.tool_priority:
            resolved = resolve_tool_name(tool)
            if whitelist is not None and not whitelist.is_allowed(resolved):
                continue
            return resolved

        return KeywordSearchAgent.pick_tool(
            task, whitelist, agent_tool_definitions, state=state
        )

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        output = await super().run(state, arguments, prompt_context)
        output["subagent"] = self._SUBAGENT_NAME
        return output
