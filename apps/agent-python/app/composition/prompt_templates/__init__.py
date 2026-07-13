"""Composition prompt template access."""

from pathlib import Path

COMPOSITION_PROMPTS_DIR = Path(__file__).resolve().parent


def list_prompt_templates() -> list[str]:
    return sorted(path.name for path in COMPOSITION_PROMPTS_DIR.glob("composer_*.md"))


def read_prompt_template(name: str) -> str:
    if "/" in name or "\\" in name:
        raise ValueError("Prompt template name must not contain path separators")
    path = COMPOSITION_PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(name)
    return path.read_text(encoding="utf-8")
