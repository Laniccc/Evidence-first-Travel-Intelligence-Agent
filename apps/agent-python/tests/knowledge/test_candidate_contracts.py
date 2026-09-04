from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.evidence.claim_decision import TransientEvidence
from app.evidence.knowledge.candidate import KnowledgeCandidate
from app.integrations.mcp.contracts import McpEvidenceEnvelope


def candidate():
    return dict(attraction_id="palace", fact_type="general_description", fact_text="景山前街4号",
                references=[dict(evidence_id="e1", field_path="/address", quote="景山前街4号")])


@pytest.mark.parametrize("extra", ["status", "publish", "source_url", "authority_score"])
def test_candidate_cannot_grant_itself_trust(extra):
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate({**candidate(), extra: "active"})


@pytest.mark.parametrize("updates", [
    {"references": []}, {"fact_type": "unknown"},
    {"references": [{"evidence_id": "e1", "field_path": "address", "quote": "x"}]},
    {"references": [{"evidence_id": "e1", "field_path": "/address", "quote": "x", "url": "fake"}]},
])
def test_grounding_contract_is_required(updates):
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate({**candidate(), **updates})


def test_candidate_valid():
    assert KnowledgeCandidate.model_validate(candidate()).references[0].field_path == "/address"


def envelope(**changes):
    kwargs = dict(server="baidu", tool="detail", tool_schema={"type": "object"},
                  payload={"address": "景山前街4号"}, provider_entity_id="uid1",
                  attraction_id="palace", source_url="https://map.baidu.com/poi/uid1",
                  retrieved_at=datetime(2026, 9, 4, tzinfo=UTC))
    kwargs.update(changes)
    return McpEvidenceEnvelope.capture(**kwargs)


def test_envelope_is_immutable_and_computes_hashes_and_call_identity():
    first, second = envelope(), envelope()
    assert first.call_id != second.call_id
    assert first.payload_hash == second.payload_hash
    assert len(first.schema_hash) == 64
    assert first.sanitized_fields[0].field_path == "/address"
    with pytest.raises(ValidationError):
        first.server = "forged"
    with pytest.raises(ValidationError):
        first.sanitized_fields[0].value = "changed"
    assert first == McpEvidenceEnvelope.model_validate_json(first.model_dump_json())


@pytest.mark.parametrize("changes", [
    {"retrieved_at": datetime(2026, 9, 4)},
    {"source_url": "file:///secret"}, {"source_url": "https://example.com/?ak=secret"},
    {"source_url": "https://user:password@example.com/"},
])
def test_envelope_rejects_invalid_time_or_unsafe_source(changes):
    with pytest.raises(ValueError):
        envelope(**changes)


def test_transient_legacy_compatible_but_new_entrypoint_requires_provenance():
    now = datetime.now(UTC)
    legacy = dict(evidence_id="e1", attraction_id="palace", fact_type="general_description",
                  content="地址", source_name="百度", source_url="https://map.baidu.com/",
                  retrieved_at=now)
    assert TransientEvidence(**legacy).provenance_ref is None
    with pytest.raises(ValueError):
        TransientEvidence.from_verified_payload(**legacy)
    from hashlib import sha256
    current = TransientEvidence.from_verified_payload(
        **legacy, subtask_id="s1", content_hash=sha256("地址".encode()).hexdigest(),
        valid_to=now + timedelta(hours=1), provenance_ref="call-1",
    )
    assert current.subtask_id == "s1"
    with pytest.raises(ValueError):
        TransientEvidence.from_verified_payload(**current.model_dump(exclude={"content_hash"}), content_hash="0" * 64)
