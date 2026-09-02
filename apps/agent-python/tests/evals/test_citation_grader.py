from evals.graders.citation import CitationCaseResult, grade_citations


def test_citation_grader_counts_false_support_and_abstention():
    metrics = grade_citations(
        [
            CitationCaseResult(
                case_id="valid",
                expected_supported=True,
                actual_supported=True,
                expected_abstain=False,
                actual_abstain=False,
            ),
            CitationCaseResult(
                case_id="expired",
                expected_supported=False,
                actual_supported=False,
                expected_abstain=True,
                actual_abstain=True,
            ),
        ]
    )

    assert metrics.citation_precision == 1.0
    assert metrics.unsupported_hard_facts == 0
    assert metrics.abstention_precision == 1.0
