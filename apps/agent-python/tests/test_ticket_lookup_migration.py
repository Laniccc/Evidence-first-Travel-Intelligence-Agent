from types import SimpleNamespace

from app.evidence.evidence_model import Claim, ClaimType, Evidence, SourceType
from app.planning.ticket_lookup_helpers import build_ticket_product_detail_retry
from app.evidence.ticket_price_extractor import extract_ticket_price_from_evidence
from app.integrations.mcp.tool_arguments import enrich_mcp_tool_arguments


def _platform_evidence(*claims: Claim) -> Evidence:
    return Evidence(
        source_name="ticket-platform",
        source_type=SourceType.TICKET_PLATFORM,
        source_url="https://tickets.example/products/boat-1",
        country="CN",
        claims=list(claims),
    )


def test_structured_ticket_product_without_price_builds_targeted_retry() -> None:
    evidence = _platform_evidence(
        Claim(claim_type=ClaimType.ACTIVITY_PRICE, value="Lake cruise adult ticket"),
        Claim(
            claim_type=ClaimType.PLATFORM_TICKET_URL,
            value="https://tickets.example/products/boat-1/detail",
        ),
    )

    assert extract_ticket_price_from_evidence([evidence], claim_type="boat_ticket_price") == []

    retry = build_ticket_product_detail_retry([evidence], claim_type="boat_ticket_price")

    assert retry is not None
    assert retry["reason"] == "structured_ticket_product_without_price"
    assert retry["hook_findings"][0]["type"] == "structured_ticket_product_without_price"
    assert retry["evidence_gap"] == {
        "missing_evidence_need": "ticket_product_price",
        "price_lookup_mode": "ticket_product_detail",
        "product_candidates": ["Lake cruise adult ticket"],
        "detail_urls": [
            "https://tickets.example/products/boat-1/detail",
            "https://tickets.example/products/boat-1",
        ],
        "require_price_fields": True,
    }


def test_price_bearing_product_does_not_request_product_detail_retry() -> None:
    evidence = _platform_evidence(
        Claim(
            claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
            value="Lake cruise adult ticket price 120 CNY",
        ),
        Claim(claim_type=ClaimType.TICKET_TYPE, value="Lake cruise adult ticket"),
    )

    assert build_ticket_product_detail_retry([evidence], claim_type="boat_ticket_price") is None


def test_ticket_detail_retry_parameters_reach_mcp_payload() -> None:
    state = SimpleNamespace(
        user_goal=None,
        semantic_frame=None,
        raw_user_query="lake cruise ticket price",
        user_need_residual=None,
        response_contract=None,
        evidence=[],
        structured_result={},
        limitations=[],
    )
    retry_parameters = {
        "price_lookup_mode": "ticket_product_detail",
        "product_candidates": ["Lake cruise adult ticket"],
        "detail_urls": ["https://tickets.example/products/boat-1/detail"],
        "require_price_fields": True,
    }

    payload = enrich_mcp_tool_arguments(
        "search_mcp",
        {"query": "Lake cruise adult ticket price"},
        state=state,
        prompt_context={
            "gap_filling": True,
            "gap_request": {"tool_parameters": retry_parameters},
        },
    )

    for key, value in retry_parameters.items():
        assert payload[key] == value
