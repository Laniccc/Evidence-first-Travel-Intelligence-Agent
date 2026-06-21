from pydantic import BaseModel, Field


class FinalAnswerSection(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


class FinalAnswerDraft(BaseModel):
    """Structured composition output — must be grounded in provided evidence."""

    headline: str = ""
    conclusion: str = ""
    sections: list[FinalAnswerSection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    answer_text: str = ""
    compose_mode: str = "advisory"

    def render_text(self) -> str:
        if self.answer_text:
            return self.answer_text
        lines = [self.headline, "", "结论：", self.conclusion]
        for section in self.sections:
            lines.extend(["", f"{section.title}：", *[f"- {b}" for b in section.bullets]])
        if self.limitations:
            lines.extend(["", "说明：", *[f"- {l}" for l in self.limitations]])
        return "\n".join(lines)
