from pydantic import BaseModel, Field

from app.composition.answer_claim import AnswerClaim


class FinalAnswerSection(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


class FinalAnswerDraft(BaseModel):
    """Structured composition output, grounded in provided evidence."""

    headline: str = ""
    conclusion: str = ""
    sections: list[FinalAnswerSection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    answer_claims: list[AnswerClaim] = Field(default_factory=list)
    answer_text: str = ""
    compose_mode: str = "advisory"

    def render_text(self) -> str:
        if self.answer_text:
            return self.answer_text
        lines = [self.headline, "", "Conclusion:", self.conclusion]
        for section in self.sections:
            lines.extend(["", f"{section.title}:", *[f"- {b}" for b in section.bullets]])
        if self.limitations:
            lines.extend(["", "Limitations:", *[f"- {l}" for l in self.limitations]])
        return "\n".join(lines)
