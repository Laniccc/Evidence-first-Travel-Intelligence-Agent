from __future__ import annotations

from datetime import datetime

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class WikidataMCPAdapter(BaseTravelTool):
    name = "wikidata_mcp"
    policy_name = "wikidata_mcp"
    server_name = "wikidata"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("wikidata")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("wikidata"))

        query = kwargs.get("query") or kwargs.get("place_name") or ""
        if not query:
            raise ValueError("wikidata_mcp requires query")

        search = await self._client.invoke("wikidata", "search_entity", {"query": str(query)})
        if not search.ok:
            raise RuntimeError(search.error or "search_entity failed")

        entity_id = self._first_entity_id(search.data)
        if not entity_id:
            raise RuntimeError(f"No Wikidata entity for {query!r}")

        meta = await self._client.invoke(
            "wikidata",
            "get_metadata",
            {"entity_id": entity_id, "language": kwargs.get("language") or "en"},
        )
        if not meta.ok:
            raise RuntimeError(meta.error or "get_metadata failed")

        text = text_from_mcp_payload(meta.data)
        props = await self._client.invoke("wikidata", "get_properties", {"entity_id": entity_id})
        if props.ok:
            text = f"{text}\n{text_from_mcp_payload(props.data)}"[:2500]

        # Determine claim type from the information need context
        claim_type = self._claim_type_for_need(kwargs.get("information_need"))
        return [
            Evidence(
                source_name="Wikidata MCP",
                source_type=SourceType.WEB,
                source_url=f"https://www.wikidata.org/wiki/{entity_id}",
                country=kwargs.get("country") or "Unknown",
                city=kwargs.get("city"),
                place_name=kwargs.get("place_name"),
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.STALE,
                license_scope=LicenseScope.PUBLIC_PAGE,
                confidence=0.82,
                claims=[
                    Claim(
                        claim_type=claim_type,
                        value=text[:800],
                        raw_text=text[:2000],
                        confidence=0.82,
                        normalized_value={"entity_id": entity_id},
                    )
                ],
                limitations=["Wikidata entity resolution."],
            )
        ]

    @staticmethod
    def _claim_type_for_need(information_need: str | None) -> ClaimType:
        """Map information need to appropriate claim type for Wikidata results."""
        if not information_need:
            return ClaimType.GENERAL_FACT
        need = str(information_need).lower()
        if need in ("elevation", "altitude", "height", "海拔"):
            return ClaimType.ELEVATION
        if need in ("general_fact", "fact_lookup", "fact"):
            return ClaimType.GENERAL_FACT
        return ClaimType.GENERAL_FACT

    @staticmethod
    def _first_entity_id(data) -> str | None:
        if isinstance(data, str) and data.startswith("Q"):
            return data
        if isinstance(data, dict):
            if "entity_id" in data:
                return str(data["entity_id"])
            for key in ("results", "search", "entities"):
                bucket = data.get(key)
                if isinstance(bucket, list) and bucket:
                    first = bucket[0]
                    if isinstance(first, dict):
                        eid = first.get("id") or first.get("entity_id")
                        if eid:
                            return str(eid)
        return None
