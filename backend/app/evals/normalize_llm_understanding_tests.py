import pytest

from app.agents.llm_understanding_agent import LLMUnderstandingSubAgent
from app.agents.normalize_llm_understanding import normalize_llm_understanding_payload
from app.schemas.normalized_user_request import NormalizedUserRequest


def test_normalize_entity_name_to_text():
    data = normalize_llm_understanding_payload(
        {
            "entities": [{"name": "喀纳斯湖", "entity_type": "natural_site", "country": "China"}],
            "confidence": {"overall": 0.96, "entity_parsing": 0.95},
            "decision_type": "best_time_to_visit",
            "task_family": "advisory",
            "query_scope": "place",
        },
        "喀纳斯湖适合几月份去",
    )
    assert data["entities"][0]["text"] == "喀纳斯湖"
    assert data["confidence"] == 0.96
    NormalizedUserRequest.model_validate(data)


def test_normalize_confidence_average():
    data = normalize_llm_understanding_payload(
        {"confidence": {"entity_parsing": 0.9, "intent": 0.8}},
        "test",
    )
    assert data["confidence"] == pytest.approx(0.85, abs=0.01)


def test_parse_and_validate_deepseek_style_payload():
    raw = """
    {
      "raw_query": "喀纳斯湖适合几月份去",
      "rewritten_query": "喀纳斯湖最佳出行月份",
      "query_scope": "place",
      "task_family": "advisory",
      "decision_type": "best_time_to_visit",
      "entities": [{"name": "喀纳斯湖", "entity_type": "lake", "country": "China", "region": "新疆"}],
      "confidence": {"overall": 0.96},
      "answer_policy": {"can_answer_with_model_prior": true},
      "information_needs": ["best_time_to_visit", "seasonality"]
    }
    """
    result = LLMUnderstandingSubAgent._parse_and_validate(raw, "喀纳斯湖适合几月份去")
    assert result.entities[0].text == "喀纳斯湖"
    assert result.entities[0].entity_type == "natural_site"
    assert result.confidence == 0.96
    assert result.answer_policy.can_answer_with_model_prior is True
