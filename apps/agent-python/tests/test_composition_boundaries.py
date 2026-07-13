from pathlib import Path

from app.composition import (
    AnswerComposerAgent,
    ComposerAgent,
    ResponseContract,
    ResponseContractCompiler,
    sanitize_answer_text,
)
from app.composition.prompt_templates import list_prompt_templates, read_prompt_template


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _composition_python_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (APP_ROOT / "composition").rglob("*.py")
    )


def test_composition_facades_export_current_capabilities():
    assert AnswerComposerAgent is not None
    assert ComposerAgent is not None
    assert ResponseContract is not None
    assert ResponseContractCompiler is not None
    assert sanitize_answer_text("hello") == "hello"


def test_composition_prompt_templates_are_owned_by_final_prompt_path():
    composition_dir = APP_ROOT / "composition" / "prompt_templates"
    expected_templates = sorted(path.name for path in composition_dir.glob("composer_*.md"))
    composition_templates = list_prompt_templates()

    assert composition_templates == expected_templates
    assert "composer_direct_fact.md" in composition_templates
    assert read_prompt_template("composer_direct_fact.md") == (
        composition_dir / "composer_direct_fact.md"
    ).read_text(encoding="utf-8")


def test_composition_layer_does_not_import_concrete_tool_execution_modules():
    text = _composition_python_text()

    forbidden = [
        "app.execution",
        "app.integrations",
        "app.tools",
        "ToolRegistry",
        "CALL_TOOL",
        "run_delegated_mcp",
        "JavaToolGateway",
    ]
    assert not [token for token in forbidden if token in text]
