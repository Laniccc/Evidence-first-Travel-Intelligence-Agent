"""Server-created immutable provenance. Input must already be allowlisted/sanitized."""

from datetime import datetime
from hashlib import sha256
import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator


def digest_json(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class McpField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field_path: str = Field(min_length=1, max_length=500, pattern=r"^/(?:[^~]|~[01])*$")
    value: str = Field(min_length=1, max_length=6000)


class McpEvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=200)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    call_id: str = Field(min_length=1, max_length=200)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: AwareDatetime
    provider_entity_id: str = Field(min_length=1, max_length=200)
    attraction_id: str = Field(min_length=1, max_length=200)
    sanitized_fields: tuple[McpField, ...] = Field(min_length=1, max_length=32)
    source_url: HttpUrl

    @field_validator("source_url")
    @classmethod
    def reject_credentials(cls, value: HttpUrl) -> HttpUrl:
        parts = urlsplit(str(value))
        sensitive = {"ak", "key", "api_key", "apikey", "token", "access_token", "secret", "signature"}
        if parts.username or parts.password or parts.fragment or any(
            key.casefold() in sensitive for key, _ in parse_qsl(parts.query)
        ):
            raise ValueError("source URL must not contain credentials or fragments")
        return value

    @classmethod
    def capture(cls, *, server: str, tool: str, tool_schema: dict,
                payload: dict[str, str], provider_entity_id: str, attraction_id: str,
                source_url: str, retrieved_at: datetime,
                call_id: str | None = None) -> "McpEvidenceEnvelope":
        # Hash the exact retained payload, not arbitrary full provider responses.
        fields = tuple(McpField(field_path="/" + key.replace("~", "~0").replace("/", "~1"),
                                value=value) for key, value in sorted(payload.items()))
        return cls(server=server, tool=tool, schema_hash=digest_json(tool_schema),
                   call_id=call_id or str(uuid4()), payload_hash=digest_json(payload),
                   retrieved_at=retrieved_at, provider_entity_id=provider_entity_id,
                   attraction_id=attraction_id, sanitized_fields=fields, source_url=source_url)
