"""Bounded extraction only; this model has no tool or database authority."""
import asyncio
from hashlib import sha256
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.evidence.knowledge.candidate import KnowledgeCandidate
from app.evidence.knowledge.promotion_policy import ALLOWED_POINTERS


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[KnowledgeCandidate] = Field(max_length=4)


class ExtractionResult(BaseModel):
    candidates: list[KnowledgeCandidate] = Field(default_factory=list)
    attempts: int = 0
    failure_code: str | None = None
    prompt_hash: str = ""
    schema_hash: str = ""


class CandidateExtractor:
    def __init__(self, model, *, timeout_seconds=8, max_tokens=2048):
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.prompt = Path(__file__).with_name("prompts").joinpath("candidate.system.md").read_text(encoding="utf-8")

    async def extract(self, envelopes) -> ExtractionResult:
        result = ExtractionResult(prompt_hash=sha256(self.prompt.encode()).hexdigest(),
            schema_hash=sha256(json.dumps(CandidateBatch.model_json_schema(), sort_keys=True).encode()).hexdigest())
        # No full response, URLs, identity tokens, or model-controlled policy fields.
        data = [{"evidence_id": e.call_id, "attraction_id": e.attraction_id,
                 "fields": {f.field_path: f.value for f in e.sanitized_fields
                            if f.field_path in ALLOWED_POINTERS.values() and len(f.value) <= 2000}}
                for e in envelopes[:4]]
        user = json.dumps({"untrusted_evidence": data}, ensure_ascii=False)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                for attempt in range(2):
                    result.attempts += 1
                    raw = await self.model.complete(system=self.prompt, user=user + (
                        "\nPrevious output was invalid; return strictly the JSON schema." if attempt else ""),
                        max_tokens=self.max_tokens)
                    try:
                        if len(raw) > 32768:
                            raise ValueError("oversize")
                        result.candidates = CandidateBatch.model_validate_json(raw).candidates
                        result.failure_code = None
                        return result
                    except (ValidationError, ValueError):
                        result.failure_code = "candidate_schema_invalid"
        except TimeoutError:
            result.failure_code = "candidate_timeout"
        except Exception:
            result.failure_code = "candidate_transport_failure"
        return result
