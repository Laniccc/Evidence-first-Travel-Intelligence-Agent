from app.governance.failure_reason import FailureClass
from app.governance.tool_budget import RunBudget
from app.orchestration.state_contracts import RecoveryRecord


def test_state_budget_and_recovery_records_are_auditable():
    budget = RunBudget(max_steps=4, max_tool_calls=2).consume_step().consume_tool_call()
    recovery = RecoveryRecord(
        strategy="deterministic_fallback",
        recovered_from=FailureClass.PARSE_ERROR,
        attempt=2,
    )

    assert budget.used_steps == 1
    assert budget.used_tool_calls == 1
    assert recovery.attempt == 2
