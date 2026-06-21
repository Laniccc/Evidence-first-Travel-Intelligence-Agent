from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tool_gateway.config import get_tool_gateway_config
from app.tool_gateway.converters import evidence_list_from_gateway, tool_trace_from_gateway
from app.tool_gateway.java_client import JavaToolGatewayClient, JavaToolGatewayUnavailable

logger = logging.getLogger(__name__)
_CLIENT: JavaToolGatewayClient | None = None


def install_java_tool_gateway() -> None:
    """Warm up Java gateway client when enabled (ActionExecutor calls try_java_tool_gateway)."""
    global _CLIENT
    config = get_tool_gateway_config()
    if not config.use_java_tool_gateway:
        logger.info("USE_JAVA_TOOL_GATEWAY=false — local tool path unchanged")
        _CLIENT = None
        return
    _CLIENT = JavaToolGatewayClient(config)
    logger.info("Java Tool Gateway enabled: %s", config.base_url)


async def try_java_tool_gateway(
    executor,
    policy_tool_name: str,
    resolved: str,
    payload: dict[str, Any],
    state: Any,
    prompt_context: dict[str, Any],
    trace_before: int,
):
    """Return ActionResult when routed to Java; None to continue with local tools."""
    from app.tools.tool_name_resolver import is_mcp_policy_tool

    config = get_tool_gateway_config()
    if not config.use_java_tool_gateway:
        return None
    if not _should_route_to_java(policy_tool_name, resolved, is_mcp_policy_tool):
        return None

    client = _CLIENT or JavaToolGatewayClient(config)
    gateway_body = _build_gateway_request(policy_tool_name, payload, state)

    try:
        gateway_result = await asyncio.to_thread(client.call_tool, gateway_body)
        return _gateway_action_result(
            executor,
            policy_tool_name,
            resolved,
            payload,
            state,
            prompt_context,
            trace_before,
            gateway_result,
        )
    except JavaToolGatewayUnavailable as exc:
        limitation = f"Java Tool Gateway unavailable for {policy_tool_name}: {exc}"
        logger.warning(limitation)
        if hasattr(state, "limitations"):
            state.limitations.append(limitation)
        return None
    except Exception as exc:
        limitation = f"Java Tool Gateway error for {policy_tool_name}: {exc}"
        logger.warning(limitation)
        if hasattr(state, "limitations"):
            state.limitations.append(limitation)
        return None


def _should_route_to_java(policy_tool_name: str, resolved: str, is_mcp_policy_tool) -> bool:
    return (
        is_mcp_policy_tool(policy_tool_name)
        or policy_tool_name.endswith("_mcp")
        or resolved.endswith("_mcp")
    )


def _build_gateway_request(tool_name: str, arguments: dict[str, Any], state: Any) -> dict[str, Any]:
    body = {
        "tool_name": tool_name,
        "arguments": arguments,
    }
    session_id = getattr(state, "session_id", None)
    query_id = getattr(state, "query_id", None)
    if session_id:
        body["session_id"] = session_id
    if query_id:
        body["query_id"] = query_id
    return body


def _gateway_action_result(
    executor,
    policy_tool_name: str,
    resolved: str,
    payload: dict[str, Any],
    state: Any,
    prompt_context: dict[str, Any],
    trace_before: int,
    gateway_result: dict[str, Any],
) -> Any:
    from app.orchestrator.actions import ActionResult

    ok = bool(gateway_result.get("ok"))
    evidence_items = evidence_list_from_gateway(list(gateway_result.get("evidence") or []))
    trace = tool_trace_from_gateway(gateway_result.get("tool_trace"), policy_tool_name, payload)

    if executor.tools is not None:
        executor.tools.traces.append(trace)
        executor._annotate_traces(trace_before, policy_tool_name, prompt_context)
        new_traces = executor.tools.traces[trace_before:]
    else:
        new_traces = [trace]

    limitation = gateway_result.get("error")
    if limitation and hasattr(state, "limitations"):
        state.limitations.append(str(limitation))

    if not ok:
        return ActionResult(
            ok=False,
            error=str(limitation or f"Java gateway rejected tool {policy_tool_name}"),
            output={
                "evidence": evidence_items,
                "tool_name": resolved,
                "policy_tool_name": policy_tool_name,
                "tool_traces": [t.model_dump() for t in new_traces],
            },
        )

    return ActionResult(
        output={
            "evidence": evidence_items,
            "tool_name": resolved,
            "policy_tool_name": policy_tool_name,
            "tool_traces": [t.model_dump() for t in new_traces],
        }
    )
