"""Five fail-closed checks; decisions and provenance are assigned by code."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import re
from urllib.parse import urlsplit, parse_qs
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.contracts.mcp_evidence import digest_json
from app.evidence.knowledge.candidate import KnowledgeCandidate
from app.evidence.knowledge.models import Attraction, FactChunkDraft, KnowledgeDocument, SourceType
from app.evidence.knowledge.promotion_policy import ALLOWED_POINTERS, PromotionPolicy


def normalize(text):
    return " ".join(text.split())


class PromotionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    outcome: Literal["rejected", "auto_publish", "manual_review"]
    reason_codes: list[str]
    evidence_refs: list[str]
    policy_version: str


def retained_payload(envelope):
    payload = {}
    seen = set()
    for field in envelope.sanitized_fields:
        if field.field_path in seen:
            raise ValueError("duplicate_pointer")
        seen.add(field.field_path)
        keys = [k.replace("~1", "/").replace("~0", "~") for k in field.field_path.split("/")[1:]]
        current = payload
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = field.value
    return payload


class PromotionValidator:
    def __init__(self, policy: PromotionPolicy, *, clock=None):
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(UTC))

    def validate(self, raw, envelopes) -> PromotionDecision:
        raw = raw.model_dump(mode="json") if isinstance(raw, KnowledgeCandidate) else raw
        candidate_id = "cand-" + digest_json(raw)
        refs = []

        def decision(code, outcome="rejected"):
            return PromotionDecision(candidate_id=candidate_id, outcome=outcome,
                reason_codes=[code], evidence_refs=refs, policy_version=self.policy.version)

        # 1. Schema: do not accept model_copy/construct as a validation bypass.
        try:
            candidate = KnowledgeCandidate.model_validate(raw)
        except ValidationError:
            return decision("schema_invalid")
        pointer = ALLOWED_POINTERS.get(candidate.fact_type.value)
        if pointer is None:
            return decision("fact_not_allowlisted")
        refs.extend(r.evidence_id for r in candidate.references)
        index = {e.call_id: e for e in envelopes}
        if len(index) != len(envelopes):
            return decision("ambiguous_evidence_id")
        selected = []
        # 2. Grounding: exact extraction from the single allowed typed field.
        for ref in candidate.references:
            envelope = index.get(ref.evidence_id)
            if envelope is None:
                return decision("evidence_missing")
            if candidate.attraction_id != envelope.attraction_id:
                return decision("attraction_mismatch")
            value = {f.field_path: f.value for f in envelope.sanitized_fields}.get(pointer)
            if ref.field_path != pointer or value is None:
                return decision("field_not_allowed")
            if normalize(candidate.fact_text) != normalize(value) or normalize(ref.quote) != normalize(value):
                return decision("grounding_mismatch")
            if re.search(r"ignore.*instructions|忽略.*指令|设置.*active|<script", value, re.I):
                return decision("unsafe_provider_content")
            selected.append(envelope)
        # 3. Provenance: trust the validated provider identity, not model labels.
        for envelope in selected:
            if envelope.server != "baidu-map" or envelope.tool != "map_place_details":
                return decision("provider_not_allowed")
            try:
                payload = retained_payload(envelope)
                if digest_json(payload) != envelope.payload_hash:
                    return decision("payload_hash_mismatch")
            except (ValueError, TypeError, AttributeError):
                return decision("payload_hash_mismatch")
            parts = urlsplit(str(envelope.source_url))
            uid = envelope.provider_entity_id
            bound_url = parts.path.rstrip("/").endswith("/" + uid) or parse_qs(parts.query).get("uid") == [uid]
            if (payload.get("uid") != uid or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", uid)
                or parts.scheme != "https" or parts.hostname not in {"map.baidu.com", "www.baidu.com", "api.map.baidu.com"}
                or not bound_url):
                return decision("provider_binding_mismatch")
        if len({e.provider_entity_id for e in selected}) != 1:
            return decision("provider_binding_mismatch")
        # 4. Temporal: snapshots cannot establish historical/future applicability.
        now = self.clock()
        for envelope in selected:
            age = (now - envelope.retrieved_at).total_seconds()
            if age < 0:
                return decision("source_future")
            if age >= self.policy.source_max_age_seconds:
                return decision("source_expired")
        ttl = self.policy.ttl(candidate.fact_type.value)
        if not 0 < ttl <= (7 * 86400 if candidate.fact_type.value == "general_description" else 3600):
            return decision("ttl_exceeds_policy")
        # 5. Persistence policy defaults to deny; opening hours never auto-publish.
        if not self.policy.storage_allowed(selected[0].server, candidate.fact_type.value):
            return decision("storage_not_permitted")
        if candidate.fact_type.value == "opening_hours":
            return decision("high_impact_manual_review", "manual_review")
        return decision("stable_address_allowed", "auto_publish")

    def document(self, decision, raw, envelopes, *, name):
        # Revalidate at the write boundary rather than trusting a supplied decision.
        actual = self.validate(raw, envelopes)
        if actual != decision or actual.outcome == "rejected":
            raise ValueError("promotion_not_validated")
        candidate = KnowledgeCandidate.model_validate(raw)
        env = next(e for e in envelopes if e.call_id == candidate.references[0].evidence_id)
        source_id = "mcp-" + sha256(f"{env.server}:{env.provider_entity_id}:{candidate.fact_type.value}".encode()).hexdigest()
        return KnowledgeDocument(source_id=source_id,
            attraction=Attraction(attraction_id=candidate.attraction_id, name=name),
            url=str(env.source_url), title="百度地图（非景点官方公告）", source_type=SourceType.STRUCTURED,
            content=candidate.fact_text, fetched_at=env.retrieved_at, valid_from=env.retrieved_at,
            valid_to=env.retrieved_at + timedelta(seconds=self.policy.ttl(candidate.fact_type.value)),
            chunks=[FactChunkDraft(fact_type=candidate.fact_type, content=candidate.fact_text,
                locator=candidate.references[0].field_path)])
