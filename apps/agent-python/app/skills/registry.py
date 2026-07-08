"""Lightweight project-local skills.

A skill is a reusable instruction package. It is not a tool — it tells the
agent HOW to approach a class of tasks while existing tools do the work.

Adapted from ClaudeAgent_A/deepfake_research/skills/registry.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    triggers: list[str]
    path: Path
    content: str


class SkillRegistry:
    """Load and select project-local skills from skills/*/SKILL.md."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or SKILLS_ROOT

    def list_skills(self) -> list[Skill]:
        skills: list[Skill] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            try:
                skills.append(_load_skill(path))
            except OSError:
                continue
        return skills

    def get(self, name: str) -> Skill | None:
        target = _normalize(name)
        for skill in self.list_skills():
            if _normalize(skill.name) == target:
                return skill
        return None

    def select_for_query(self, query: str, *, max_skills: int = 4) -> list[Skill]:
        """Select relevant skills by matching query text against skill triggers."""
        selected: list[Skill] = []
        text = query.lower()

        for skill in self.list_skills():
            if len(selected) >= max_skills:
                break
            for trigger in skill.triggers:
                if trigger.lower() in text:
                    if skill.name not in {s.name for s in selected}:
                        selected.append(skill)
                    break

        # Core skills always active for any research query
        self._add("source-evaluation", selected)
        self._add("search-strategy", selected)
        self._add("research-synthesis", selected)

        # Context-sensitive skills
        if _contains_any(text, ["verify", "check evidence", "citation check", "事实核查", "证据检查", "引用校验"]):
            self._add("verification", selected)
        if _contains_any(text, ["paper", "pdf", "论文", "文献", "article review", "academic", "学术"]):
            self._add("paper-reading", selected)
        if _contains_any(text, ["github", "repo", "repository", "codebase", "仓库", "源代码", "项目结构"]):
            self._add("repo-analysis", selected)
        if _contains_any(text, ["extract", "claim", "fetch", "抓取", "提取", "声明"]):
            self._add("evidence-extraction", selected)

        return selected[:max_skills]

    def _add(self, name: str, selected: list[Skill]) -> None:
        skill = self.get(name)
        if skill and skill.name not in {s.name for s in selected}:
            selected.append(skill)

    def render_prompt_block(self, skills: list[Skill]) -> str:
        """Render selected skills as a prompt section for the agent."""
        if not skills:
            return ""
        parts = [
            "## Activated Research Skills",
            "Use these structured workflows when performing your task.",
            "",
        ]
        for skill in skills:
            parts.append(
                f"### Skill: {skill.name}\n"
                f"{skill.content.strip()}\n"
            )
        return "\n".join(parts).strip()


def _load_skill(path: Path) -> Skill:
    raw = path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(raw)
    name = metadata.get("name") or path.parent.name
    description = metadata.get("description") or ""
    triggers = [
        item.strip()
        for item in (metadata.get("triggers") or "").split(",")
        if item.strip()
    ]
    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        path=path,
        content=body,
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta_raw = parts[1]
    body = parts[2].strip()
    metadata: dict[str, str] = {}
    for line in meta_raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, body


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower() in text for needle in needles)
