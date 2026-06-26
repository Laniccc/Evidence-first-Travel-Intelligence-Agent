"""CLI mode resolution tests."""

from __future__ import annotations

from tools.crawlers.cli_mode import resolve_crawler_cli_mode


def test_review_claim_maps_to_review_mode():
    assert resolve_crawler_cli_mode(crawler_mode=None, claim_type="review_summary") == "review"


def test_explicit_crawler_mode_wins():
    assert resolve_crawler_cli_mode(crawler_mode="ticket", claim_type="review_summary") == "ticket"


def test_nearby_food_maps_to_nearby():
    assert resolve_crawler_cli_mode(crawler_mode="nearby", claim_type="nearby_food") == "nearby"
