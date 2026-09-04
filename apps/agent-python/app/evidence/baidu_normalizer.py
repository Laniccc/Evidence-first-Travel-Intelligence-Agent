"""Extractive evidence from a verified, retained provider field."""

from datetime import timedelta
from hashlib import sha256
import re

from app.contracts.mcp_evidence import McpEvidenceEnvelope
from app.evidence.claim_decision import TransientEvidence


class BaiduEvidenceError(ValueError):
    pass


def normalize_baidu_evidence(envelope: McpEvidenceEnvelope, *, fact_type: str,
                             subtask_id: str) -> TransientEvidence:
    pointer = {"opening_hours": "/detail_info/shop_hours",
               "general_description": "/address"}.get(fact_type)
    if pointer is None:
        raise BaiduEvidenceError("unsupported_fact")
    fields = {field.field_path: field.value for field in envelope.sanitized_fields}
    content = fields.get(pointer, "").strip()
    if not content:
        raise BaiduEvidenceError("required_field_missing")
    if len(content) > 2000 or re.search(r"ignore.*instructions|忽略.*指令|设置.*active|<script", content, re.I):
        raise BaiduEvidenceError("unsafe_provider_content")
    return TransientEvidence.from_verified_payload(
        evidence_id="mcp:" + envelope.call_id + ":" + fact_type,
        attraction_id=envelope.attraction_id, fact_type=fact_type, content=content,
        source_name="百度地图（非景点官方公告）", source_url=str(envelope.source_url),
        retrieved_at=envelope.retrieved_at, valid_to=envelope.retrieved_at + timedelta(hours=1),
        subtask_id=subtask_id, content_hash=sha256(content.encode()).hexdigest(),
        provenance_ref=envelope.call_id,
    )
