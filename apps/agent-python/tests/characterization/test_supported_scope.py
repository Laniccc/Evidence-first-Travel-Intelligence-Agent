from enum import StrEnum


class SupportedTask(StrEnum):
    FACT_QUERY = "fact_query"
    SUITABILITY = "suitability"
    COMPARISON = "comparison"
    CLARIFICATION = "clarification"


SUPPORTED_TASKS = {task.value for task in SupportedTask}
RETIRED_CAPABILITY_MARKERS = {
    "itinerary",
    "nearby",
    "crowd_estimation",
    "review_crawler",
    "ticket_crawler",
}


def test_supported_product_scope_is_intentionally_small():
    assert SUPPORTED_TASKS == {
        "fact_query",
        "suitability",
        "comparison",
        "clarification",
    }


def test_retired_capabilities_are_recorded_before_pruning():
    assert RETIRED_CAPABILITY_MARKERS == {
        "itinerary",
        "nearby",
        "crowd_estimation",
        "review_crawler",
        "ticket_crawler",
    }
