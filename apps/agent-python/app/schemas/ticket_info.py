"""Structured ticket provider payloads before Evidence normalization."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.review_signal import ReviewSignalClaim

# Backward-compatible alias; prefer ReviewSignalClaim from review_signal.py.
TicketReviewSignal = ReviewSignalClaim


class TicketInfoClaim(BaseModel):
    place_name: str
    normalized_place_id: str | None = None
    provider: str
    source_url: str | None = None
    ticket_type: str | None = None
    price: float | None = None
    currency: str | None = "CNY"
    price_text: str | None = None
    available_date: str | None = None
    booking_channel: str | None = None
    reservation_required: bool | None = None
    refund_policy: str | None = None
    sales_status: str | None = None
    confidence: float = 0.6
    captured_at: str
    is_historical_snapshot: bool = False


class TicketSnapshot(BaseModel):
    snapshot_id: str
    place_name: str
    normalized_place_id: str | None = None
    provider: str
    ticket_type: str | None = None
    price: float | None = None
    currency: str | None = "CNY"
    price_text: str | None = None
    source_url: str | None = None
    captured_at: str
    raw_hash: str | None = None
