from __future__ import annotations

from datetime import datetime

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class SqliteMCPAdapter(BaseTravelTool):
    """SQLite evidence cache via mcp-sqlite query/read_records."""

    def __init__(self, policy_name: str, client: MCPClientManager | None = None) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = "sqlite"
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("sqlite")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("sqlite"))

        table = kwargs.get("table") or "evidence_cache"
        if kwargs.get("sql"):
            result = await self._client.invoke(
                "sqlite",
                "query",
                {"sql": kwargs["sql"], "values": kwargs.get("values") or []},
            )
        else:
            conditions = {}
            if kwargs.get("place_name"):
                conditions["place_name"] = kwargs["place_name"]
            if kwargs.get("session_id"):
                conditions["session_id"] = kwargs["session_id"]
            result = await self._client.invoke(
                "sqlite",
                "read_records",
                {"table": table, "conditions": conditions, "limit": int(kwargs.get("limit") or 5)},
            )

        if not result.ok:
            raise RuntimeError(result.error or "sqlite read failed")

        text = text_from_mcp_payload(result.data)
        return [
            Evidence(
                source_name="SQLite Evidence Cache",
                source_type=SourceType.UNKNOWN,
                source_url=None,
                country=kwargs.get("country") or "Unknown",
                city=kwargs.get("city"),
                place_name=kwargs.get("place_name"),
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.RECENT,
                license_scope=LicenseScope.UNKNOWN,
                confidence=0.6,
                claims=[
                    Claim(
                        claim_type=ClaimType.TRAVEL_ADVICE,
                        value=text[:600],
                        raw_text=text[:2000],
                        confidence=0.6,
                    )
                ],
                limitations=["Read from local evidence cache DB."],
            )
        ]
