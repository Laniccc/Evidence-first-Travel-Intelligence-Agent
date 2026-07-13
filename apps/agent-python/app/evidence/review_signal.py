"""Structured review / ticket-signal payloads before Evidence normalization."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewSignalClaim(BaseModel):
    place_name: str
    normalized_place_id: str | None = None
    provider: str
    source_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    star_distribution: dict[str, int] = Field(default_factory=dict)
    positive_aspects: list[str] = Field(default_factory=list)
    negative_aspects: list[str] = Field(default_factory=list)
    ticket_related_mentions: list[str] = Field(default_factory=list)
    booking_channel_mentions: list[str] = Field(default_factory=list)
    queue_risk: str | None = None
    crowd_risk: str | None = None
    value_for_money: str | None = None
    commercialization_risk: str | None = None
    transport_difficulty: str | None = None
    family_friendly: str | None = None
    elderly_suitability: str | None = None
    captured_at: str
    confidence: float = 0.5


class TicketSignalClaim(BaseModel):
    place_name: str
    provider: str
    source_url: str | None = None
    ticket_related_mentions: list[str] = Field(default_factory=list)
    ticket_price_candidate_text: str | None = None
    booking_channel_mentions: list[str] = Field(default_factory=list)
    reservation_mentions: list[str] = Field(default_factory=list)
    queue_or_entry_mentions: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    captured_at: str
