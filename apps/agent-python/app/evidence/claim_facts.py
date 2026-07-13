"""Structured fact schemas extracted from evidence for S7."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpeningHoursFact(BaseModel):
    open_time: str | None = None
    close_time: str | None = None
    last_entry_time: str | None = None
    last_ticket_time: str | None = None
    closed_days: list[str] = Field(default_factory=list)
    date_range: str | None = None
    season_label: str | None = None
    exception_policy: str | None = None
    source_class: str = "unknown"
    source_url: str | None = None
    evidence_strength: str = "partial"

    def summary_line(self) -> str:
        parts: list[str] = []
        if self.open_time:
            parts.append(f"开放 {self.open_time}")
        if self.last_ticket_time:
            parts.append(f"止票 {self.last_ticket_time}")
        if self.last_entry_time:
            parts.append(f"停止入馆 {self.last_entry_time}")
        if self.close_time:
            parts.append(f"闭馆 {self.close_time}")
        if self.closed_days:
            parts.append("闭馆日：" + "、".join(self.closed_days))
        if self.date_range:
            parts.append(f"适用时段 {self.date_range}")
        if self.season_label:
            parts.append(f"季节 {self.season_label}")
        return "；".join(parts) if parts else ""


class TicketPriceFact(BaseModel):
    ticket_product: str = "entrance_ticket"
    ticket_name: str | None = None

    adult_price: float | None = None
    child_price: float | None = None
    student_price: float | None = None
    senior_price: float | None = None

    discount_policy: list[str] = Field(default_factory=list)
    free_policy: list[str] = Field(default_factory=list)

    currency: str = "CNY"
    valid_date_or_season: str | None = None
    reservation_required: bool | None = None
    booking_url: str | None = None

    source_class: str = "unknown"
    source_url: str | None = None
    evidence_strength: str = "partial"
    raw_text: str | None = None

    def summary_line(self) -> str:
        price = self.adult_price
        if price is None:
            for candidate in (self.child_price, self.student_price, self.senior_price):
                if candidate is not None:
                    price = candidate
                    break
        if price is not None:
            name = self.ticket_name or self.ticket_product
            return f"{name} {price:g} {self.currency}"
        if self.raw_text:
            return self.raw_text[:120]
        return ""
