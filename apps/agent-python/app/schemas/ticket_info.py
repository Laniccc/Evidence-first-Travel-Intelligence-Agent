"""Structured ticket / review provider payloads before Evidence normalization."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class TicketReviewSignal(BaseModel):
    place_name: str
    provider: str
    source_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    positive_aspects: list[str] = Field(default_factory=list)
    negative_aspects: list[str] = Field(default_factory=list)
    ticket_related_mentions: list[str] = Field(default_factory=list)
    queue_risk: str | None = None
    crowd_risk: str | None = None
    value_for_money: str | None = None
    captured_at: str
    confidence: float = 0.5


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
