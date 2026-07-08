"""Unit tests for skill registry loading and selection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.skills.registry import SkillRegistry, Skill


def test_registry_loads_all_skills():
    registry = SkillRegistry()
    skills = registry.list_skills()
    names = {s.name for s in skills}
    # Core skills must exist
    assert "source-evaluation" in names, f"Missing core skill. Found: {names}"
    assert "search-strategy" in names, f"Missing core skill. Found: {names}"
    assert "research-synthesis" in names, f"Missing core skill. Found: {names}"
    assert "verification" in names, f"Missing skill. Found: {names}"
    assert "paper-reading" in names, f"Missing skill. Found: {names}"
    assert "repo-analysis" in names, f"Missing skill. Found: {names}"
    assert "evidence-extraction" in names, f"Missing skill. Found: {names}"
    assert len(skills) == 7, f"Expected 7 skills, got {len(skills)}: {names}"


def test_skill_has_required_fields():
    registry = SkillRegistry()
    for skill in registry.list_skills():
        assert skill.name, f"Skill {skill.path} has no name"
        assert skill.description, f"Skill {skill.name} has no description"
        assert len(skill.triggers) > 0, f"Skill {skill.name} has no triggers"
        assert len(skill.content) > 50, f"Skill {skill.name} content too short ({len(skill.content)} chars)"


def test_get_skill_by_name():
    registry = SkillRegistry()
    skill = registry.get("source-evaluation")
    assert skill is not None
    assert skill.name == "source-evaluation"
    assert "Tier" in skill.content


def test_get_skill_nonexistent():
    registry = SkillRegistry()
    assert registry.get("nonexistent-skill") is None


def test_get_skill_normalized():
    """Name matching should be case-insensitive and handle underscores."""
    registry = SkillRegistry()
    assert registry.get("Source-Evaluation") is not None
    assert registry.get("source_evaluation") is not None
    assert registry.get("SOURCE-EVALUATION") is not None


def test_select_for_query_core_skills():
    """Any query should activate core skills."""
    registry = SkillRegistry()
    selected = registry.select_for_query("What is Python?")
    names = {s.name for s in selected}
    assert "source-evaluation" in names
    assert "search-strategy" in names
    assert "research-synthesis" in names


def test_select_for_query_triggers_paper():
    """Query mentioning 'paper' or '论文' should activate paper-reading."""
    registry = SkillRegistry()
    selected = registry.select_for_query("Summarize this academic paper about transformers")
    names = {s.name for s in selected}
    assert "paper-reading" in names

    selected2 = registry.select_for_query("分析这篇论文的方法")
    names2 = {s.name for s in selected2}
    assert "paper-reading" in names2


def test_select_for_query_triggers_repo():
    """Query mentioning 'github' or 'repo' should activate repo-analysis."""
    registry = SkillRegistry()
    selected = registry.select_for_query("Analyze the LangGraph GitHub repository architecture")
    names = {s.name for s in selected}
    assert "repo-analysis" in names

    selected2 = registry.select_for_query("这个仓库的代码结构怎么样")
    names2 = {s.name for s in selected2}
    assert "repo-analysis" in names2


def test_select_for_query_triggers_verification():
    """Query mentioning 'verify' or '证据' should activate verification."""
    registry = SkillRegistry()
    selected = registry.select_for_query("Verify the evidence for these claims")
    names = {s.name for s in selected}
    assert "verification" in names

    selected2 = registry.select_for_query("检查这篇引用的证据")
    names2 = {s.name for s in selected2}
    assert "verification" in names2


def test_select_for_query_max_skills():
    """Should never exceed max_skills."""
    registry = SkillRegistry()
    # Query that could match many skills
    selected = registry.select_for_query(
        "Verify the evidence extraction from this academic paper about"
        " the LangGraph GitHub repository architecture",
        max_skills=4,
    )
    assert len(selected) <= 4


def test_render_prompt_block():
    registry = SkillRegistry()
    skills = registry.list_skills()[:2]  # just 2 for test
    block = registry.render_prompt_block(skills)
    assert "## Activated Research Skills" in block
    assert "Skill:" in block
    assert len(block) > 100


def test_render_prompt_block_empty():
    registry = SkillRegistry()
    assert registry.render_prompt_block([]) == ""


def test_skill_instantiation():
    """Skill dataclass should be immutable."""
    skill = Skill(
        name="test",
        description="A test skill",
        triggers=["test"],
        path=Path("/fake/skill.md"),
        content="Test content here.",
    )
    assert skill.name == "test"
    with pytest.raises(Exception):
        skill.name = "changed"  # frozen=True


def test_all_triggers_are_lowercase():
    """Consistency check: all triggers should be lowercase for matching."""
    registry = SkillRegistry()
    for skill in registry.list_skills():
        for trigger in skill.triggers:
            assert trigger == trigger.lower(), (
                f"Skill '{skill.name}' has non-lowercase trigger: '{trigger}'"
            )
