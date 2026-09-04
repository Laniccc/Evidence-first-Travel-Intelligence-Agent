"""Candidate content has no authority to assign source trust or publication state."""

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.knowledge.models import FactType


class GroundingRef(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    evidence_id: str = Field(min_length=1, max_length=200)
    field_path: str = Field(min_length=1, max_length=500, pattern=r"^/(?:[^~]|~[01])*$")
    quote: str = Field(min_length=1, max_length=2000)


class KnowledgeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    attraction_id: str = Field(min_length=1, max_length=200)
    fact_type: FactType
    fact_text: str = Field(min_length=1, max_length=2000)
    references: list[GroundingRef] = Field(min_length=1, max_length=4)
