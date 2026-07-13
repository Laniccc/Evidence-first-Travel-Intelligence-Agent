"""Answer composition capability layer with lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "AnswerComposerAgent": ("app.composition.answer_composer", "AnswerComposerAgent"),
    "COMPOSITION_PROMPTS_DIR": ("app.composition.prompt_templates", "COMPOSITION_PROMPTS_DIR"),
    "ClaimRequirement": ("app.composition.response_contract", "ClaimRequirement"),
    "ClarificationPolicy": ("app.composition.response_contract", "ClarificationPolicy"),
    "ComposerAgent": ("app.composition.composer", "ComposerAgent"),
    "CompositionError": ("app.composition.answer_composer", "CompositionError"),
    "CompositionPolicy": ("app.composition.response_contract", "CompositionPolicy"),
    "EntityPolicy": ("app.composition.response_contract", "EntityPolicy"),
    "FallbackPolicy": ("app.composition.response_contract", "FallbackPolicy"),
    "ItineraryAgent": ("app.composition.composer", "ItineraryAgent"),
    "ResponseContract": ("app.composition.response_contract", "ResponseContract"),
    "ResponseContractCompiler": (
        "app.composition.response_contract_compiler",
        "ResponseContractCompiler",
    ),
    "TravelSuitabilityScorer": ("app.composition.suitability_scorer", "TravelSuitabilityScorer"),
    "ToolStrategy": ("app.composition.response_contract", "ToolStrategy"),
    "clear_premature_clarification_for_composition": (
        "app.composition.composition_preflight",
        "clear_premature_clarification_for_composition",
    ),
    "has_actionable_claim_decisions": (
        "app.composition.composition_preflight",
        "has_actionable_claim_decisions",
    ),
    "is_premature_place_clarification": (
        "app.composition.composition_preflight",
        "is_premature_place_clarification",
    ),
    "is_user_visible_limitation": ("app.composition.response_sanitizer", "is_user_visible_limitation"),
    "list_prompt_templates": ("app.composition.prompt_templates", "list_prompt_templates"),
    "read_prompt_template": ("app.composition.prompt_templates", "read_prompt_template"),
    "sanitize_answer_text": ("app.composition.response_sanitizer", "sanitize_answer_text"),
    "sanitize_limitations": ("app.composition.response_sanitizer", "sanitize_limitations"),
    "should_compose_over_clarification": (
        "app.composition.composition_preflight",
        "should_compose_over_clarification",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
