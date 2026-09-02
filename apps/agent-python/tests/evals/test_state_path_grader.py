from evals.graders.state_path import StatePathCaseResult, grade_state_paths


def test_state_path_grader_counts_accuracy_and_illegal_transitions():
    metrics = grade_state_paths(
        [
            StatePathCaseResult(
                case_id="ok",
                expected_terminal="fact_query",
                actual_terminal="fact_query",
                illegal_transition_count=0,
            ),
            StatePathCaseResult(
                case_id="bad",
                expected_terminal="comparison",
                actual_terminal="clarification",
                illegal_transition_count=1,
            ),
        ]
    )

    assert metrics.path_accuracy == 0.5
    assert metrics.illegal_transitions == 1
