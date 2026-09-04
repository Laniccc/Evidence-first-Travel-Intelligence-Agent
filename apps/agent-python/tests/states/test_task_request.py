import pytest
from pydantic import ValidationError

from app.understanding.task_request import TaskRequest, to_normalized_request


def task(**updates):
    return dict(task_type="fact_query", entities=[{"name": "故宫"}],
                rewritten_query="故宫开放时间", fact_types=["opening_hours"], **updates)


def test_mapping_preserves_time_and_constraints_without_trusting_ids():
    request = TaskRequest.model_validate(task(
        requested_as_of="2026-09-06T09:00:00+08:00",
        constraints={"party": ["老人"], "constraints": ["需要轮椅通道"]},
    ))
    normalized = to_normalized_request(request, raw_query="原始问题")
    assert normalized.raw_query == "原始问题"
    assert normalized.task_family == "fact_lookup"
    assert normalized.time_scope.reference_date == "2026-09-06T09:00:00+08:00"
    assert normalized.user_constraints.constraints == ["需要轮椅通道"]
    assert normalized.information_needs[0].need_type == "opening_hours"


@pytest.mark.parametrize("updates", [
    {"task_type": "planning"}, {"top_k": 100},
    {"entities": [{"name": "故宫", "attraction_id": "trusted-id"}]},
    {"constraints": {"sql": "select *"}}, {"fact_types": ["invented"]},
    {"requested_as_of": "2026-09-06T09:00:00"},
    {"requested_as_of": "2026-09-06"}, {"entities": []},
    {"task_type": "comparison", "entities": [{"name": "故宫"}]},
])
def test_strict_task_rejects_unbounded_or_ambiguous_input(updates):
    data = task()
    data.update(updates)
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(data)


def test_clarification_accepts_no_entity_and_requires_question():
    data = task()
    data.update(task_type="clarification", entities=[], clarification_question="请提供景点名称")
    assert to_normalized_request(TaskRequest.model_validate(data), raw_query="那里呢").needs_clarification
    data["clarification_question"] = None
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(data)
