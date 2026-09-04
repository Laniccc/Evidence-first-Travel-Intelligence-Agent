"""Read-only, two-tool provider adapter. No knowledge writes or model calls."""

import asyncio
from datetime import UTC, datetime
import json
from time import perf_counter
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from app.contracts.baidu import BaiduPoiBinding
from app.contracts.mcp_evidence import McpEvidenceEnvelope
from app.integrations.mcp.tool_catalog import MCPBoundaryError


def _norm(text):
    return "".join(str(text).casefold().split())


def _city(text):
    return _norm(text).removesuffix("市")


def _data(receipt):
    content = receipt.result.get("content", [])
    if len(content) != 1 or content[0].get("type") != "text":
        raise MCPBoundaryError("malformed_payload")
    try:
        value = json.loads(content[0]["text"])
    except (ValueError, KeyError, TypeError):
        raise MCPBoundaryError("malformed_payload") from None
    if not isinstance(value, dict):
        raise MCPBoundaryError("malformed_payload")
    return value


class BaiduGapTool:
    def __init__(self, session, *, binding_resolver, clock=None,
                 deadline_seconds=20.0, tool_timeout_seconds=5.0):
        if deadline_seconds <= 0 or tool_timeout_seconds <= 0:
            raise ValueError("invalid gap deadline")
        self.session = session
        self._binding = binding_resolver
        self._clock = clock or (lambda: datetime.now(UTC))
        self._deadline = deadline_seconds
        self._tool_timeout = tool_timeout_seconds

    async def fetch_gap(self, task, *, before_call):
        if self.session.catalog is None or not getattr(self.session, "running", True):
            return {"attempts": [], "failure_code": "mcp_not_ready", "session_restarts": 0}
        attempts, restarts = [], 0

        async def call(name, arguments):
            nonlocal restarts
            self.session.catalog.validate(name, arguments)
            for attempt in (1, 2):
                before_call()
                audit = {"tool_name": name, "attempt": attempt, "status": "failed",
                         "schema_hash": self.session.catalog.hashes[name], "call_id": str(uuid4())}
                attempts.append(audit)
                started = perf_counter()
                try:
                    async with asyncio.timeout(self._tool_timeout):
                        receipt = await self.session.call_tool(name, arguments)
                    audit.update(status="success", call_id=receipt.call_id)
                    return receipt
                except asyncio.CancelledError:
                    audit["failure_code"] = "tool_cancelled"
                    raise
                except (MCPBoundaryError, TimeoutError) as exc:
                    code = exc.code if isinstance(exc, MCPBoundaryError) else "tool_timeout"
                    audit["failure_code"] = code
                    if attempt == 2 or code not in {"rate_limit", "tool_timeout", "connection_closed"}:
                        raise MCPBoundaryError(code) from None
                    if code != "rate_limit":
                        if restarts >= 1:
                            raise MCPBoundaryError("session_restart_exhausted")
                        restarts += 1
                        await self.session.restart()
                finally:
                    audit["duration_ms"] = max(0, (perf_counter() - started) * 1000)

        try:
            async with asyncio.timeout(self._deadline):
                if task.get("require_explicit_temporal_coverage"):
                    raise MCPBoundaryError("temporal_scope_unsupported")
                if task["fact_type"] not in {"opening_hours", "general_description"}:
                    raise MCPBoundaryError("unsupported_fact")
                binding = BaiduPoiBinding.model_validate(self._binding(task["attraction_id"]))
                if binding.attraction_id != task["attraction_id"]:
                    raise MCPBoundaryError("binding_mismatch")
                names = {_norm(n) for n in (binding.name, *binding.aliases)}
                uid = binding.provider_uid
                if not uid:
                    search = _data(await call("map_search_places", {"query": binding.name, "region": binding.city}))
                    rows = search.get("results", [])
                    if not isinstance(rows, list) or len(rows) > 20:
                        raise MCPBoundaryError("malformed_payload")
                    matches = {row.get("uid") for row in rows if isinstance(row, dict)
                               and _norm(row.get("name")) in names and _city(row.get("city")) == _city(binding.city)
                               and isinstance(row.get("uid"), str) and row["uid"].strip()}
                    if len(matches) != 1:
                        raise MCPBoundaryError("ambiguous_entity" if matches else "entity_not_found")
                    uid = next(iter(matches))
                arguments = {"uid": uid}
                if "scope" in self.session.catalog.schema("map_place_details").get("properties", {}):
                    arguments["scope"] = "2"
                receipt = await call("map_place_details", arguments)
                detail = _data(receipt)
                if detail.get("uid") != uid or _norm(detail.get("name")) not in names or _city(detail.get("city")) != _city(binding.city):
                    raise MCPBoundaryError("entity_mismatch")
                info = detail.get("detail_info") or {}
                if not isinstance(info, dict):
                    raise MCPBoundaryError("malformed_payload")
                url = info.get("detail_url")
                if not isinstance(url, str) or not url:
                    raise MCPBoundaryError("source_url_missing")
                parts = urlsplit(url)
                url_uid = parse_qs(parts.query).get("uid", [None])[0]
                if parts.hostname not in {"api.map.baidu.com", "map.baidu.com", "www.map.baidu.com"} or (
                    url_uid != uid and unquote(parts.path).rstrip("/").rsplit("/", 1)[-1] != uid
                ):
                    raise MCPBoundaryError("invalid_source_url")
                retained = {key: detail[key] for key in ("uid", "name", "city", "address")
                            if isinstance(detail.get(key), str) and detail[key].strip()}
                retained["detail_info"] = {key: info[key] for key in ("detail_url", "shop_hours")
                                           if isinstance(info.get(key), str) and info[key].strip()}
                try:
                    envelope = McpEvidenceEnvelope.capture(
                        server="baidu-map", tool="map_place_details",
                        tool_schema=self.session.catalog.schema("map_place_details"),
                        payload=retained, provider_entity_id=uid, attraction_id=binding.attraction_id,
                        source_url=url, retrieved_at=self._clock(), call_id=receipt.call_id)
                except ValueError:
                    raise MCPBoundaryError("invalid_source_url") from None
                return {"envelope": envelope.model_dump(mode="json"), "attempts": attempts,
                        "session_restarts": restarts}
        except (MCPBoundaryError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            code = exc.code if isinstance(exc, MCPBoundaryError) else (
                "gap_deadline_exceeded" if isinstance(exc, TimeoutError) else "malformed_payload")
            return {"failure_code": code, "attempts": attempts, "session_restarts": restarts}
