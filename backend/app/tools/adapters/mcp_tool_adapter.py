import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.tools.base import BaseTravelTool
from app.tools.mcp.client_manager import MCPClientManager, MCPInvokeResult, get_mcp_client_manager

logger = logging.getLogger(__name__)

_SERVER_SOURCE_TYPE: dict[str, SourceType] = {
    "search": SourceType.WEB,
    "browser": SourceType.OFFICIAL,
    "osm": SourceType.MAP,
    "openmeteo": SourceType.WEATHER_API,
    "wikipedia": SourceType.WEB,
    "wikidata": SourceType.WEB,
    "sqlite": SourceType.UNKNOWN,
}

_CLAIM_HINTS: dict[str, ClaimType] = {
    "opening_hours": ClaimType.OPENING_HOURS,
    "ticket_price": ClaimType.TICKET_PRICE,
    "weather": ClaimType.WEATHER,
    "seasonality": ClaimType.SEASONALITY,
    "best_time_to_visit": ClaimType.BEST_TIME_TO_VISIT,
    "crowd": ClaimType.CROWD,
    "reservation": ClaimType.RESERVATION,
    "address": ClaimType.ADDRESS,
    "travel_advice": ClaimType.TRAVEL_ADVICE,
}


class MCPToolAdapter(BaseTravelTool):
    """Generic MCP adapter — converts MCP responses into validated Evidence objects."""

    name = "mcp_tool_adapter"
    policy_name: str = "mcp_tool_adapter"
    server_name: str = ""
    default_mcp_tool: str = "generic_mcp"
    capabilities: list[str] = []

    def __init__(
        self,
        policy_name: str,
        server_name: str,
        default_mcp_tool: str,
        capabilities: list[str],
        client: MCPClientManager | None = None,
    ) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = server_name
        self.default_mcp_tool = default_mcp_tool
        self.capabilities = capabilities
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured(self.server_name)

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(f"MCP {self.policy_name} not configured")

        mcp_tool = kwargs.pop("mcp_tool", None) or kwargs.pop("tool", None) or self.default_mcp_tool
        invoke_args = dict(kwargs)
        invoke_args.setdefault("policy_tool", self.policy_name)

        result: MCPInvokeResult = await self._client.invoke(self.server_name, mcp_tool, invoke_args)
        if not result.ok:
            raise RuntimeError(result.error or f"MCP invoke failed: {self.server_name}/{mcp_tool}")

        return self._normalize_to_evidence(result.data, mcp_tool=mcp_tool, **kwargs)

    def _normalize_to_evidence(self, raw: Any, *, mcp_tool: str, **kwargs) -> list[Evidence]:
        if isinstance(raw, list):
            evidence_list: list[Evidence] = []
            for item in raw:
                if isinstance(item, Evidence):
                    evidence_list.append(item)
                elif isinstance(item, dict):
                    evidence_list.append(self._dict_to_evidence(item, mcp_tool=mcp_tool, **kwargs))
                else:
                    raise ValueError(f"Unsupported MCP payload type: {type(item)}")
            return evidence_list
        if isinstance(raw, Evidence):
            return [raw]
        if isinstance(raw, dict):
            if "evidence" in raw:
                return self._normalize_to_evidence(raw["evidence"], mcp_tool=mcp_tool, **kwargs)
            return [self._dict_to_evidence(raw, mcp_tool=mcp_tool, **kwargs)]

        text = str(raw)
        return [
            self._dict_to_evidence(
                {"text": text, "claims": [{"claim_type": "travel_advice", "value": text}]},
                mcp_tool=mcp_tool,
                **kwargs,
            )
        ]

    def _dict_to_evidence(self, payload: dict, *, mcp_tool: str, **kwargs) -> Evidence:
        if "source_name" in payload and "claims" in payload:
            try:
                return Evidence.model_validate(payload)
            except ValidationError:
                pass

        country = payload.get("country") or kwargs.get("country") or "Unknown"
        city = payload.get("city") or kwargs.get("city")
        place_name = payload.get("place_name") or kwargs.get("place_name")
        source_type = payload.get("source_type")
        if isinstance(source_type, str):
            try:
                source_type = SourceType(source_type)
            except ValueError:
                source_type = _SERVER_SOURCE_TYPE.get(self.server_name, SourceType.WEB)
        else:
            source_type = _SERVER_SOURCE_TYPE.get(self.server_name, SourceType.WEB)

        claims_raw = payload.get("claims") or []
        claims: list[Claim] = []
        for item in claims_raw:
            if isinstance(item, Claim):
                claims.append(item)
            elif isinstance(item, dict):
                ct = item.get("claim_type", "travel_advice")
                if isinstance(ct, str):
                    ct = _CLAIM_HINTS.get(ct, ClaimType.TRAVEL_ADVICE)
                claims.append(
                    Claim(
                        claim_type=ct,
                        value=item.get("value"),
                        raw_text=item.get("raw_text"),
                        normalized_value=item.get("normalized_value"),
                        confidence=float(item.get("confidence", 0.65)),
                    )
                )

        if not claims:
            text = payload.get("text") or payload.get("content") or payload.get("summary") or str(payload)
            hint = kwargs.get("information_need") or kwargs.get("need_type")
            claim_type = _CLAIM_HINTS.get(hint, ClaimType.TRAVEL_ADVICE) if hint else ClaimType.TRAVEL_ADVICE
            claims.append(Claim(claim_type=claim_type, value=text, raw_text=str(text), confidence=0.6))

        limitations = list(payload.get("limitations") or [])
        limitations.append(f"mcp_server={self.server_name}")
        limitations.append(f"mcp_tool={mcp_tool}")

        return Evidence(
            source_name=payload.get("source_name") or self.policy_name,
            source_type=source_type,
            source_url=payload.get("source_url") or payload.get("url"),
            country=country,
            city=city,
            place_name=place_name,
            retrieved_at=payload.get("retrieved_at") or datetime.utcnow(),
            data_freshness=DataFreshness.RECENT,
            license_scope=LicenseScope.PUBLIC_PAGE,
            confidence=float(payload.get("confidence", 0.65)),
            claims=claims,
            limitations=limitations,
        )


ConfiguredMCPTool = MCPToolAdapter


def validate_mcp_evidence(payload: dict) -> Evidence:
    return Evidence.model_validate(payload)
