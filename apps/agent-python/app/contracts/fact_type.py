"""Shared internal fact vocabulary; not an expansion of public API behavior."""

from enum import StrEnum


class FactType(StrEnum):
    OPENING_HOURS = "opening_hours"
    TICKET_PRICE = "ticket_price"
    RESERVATION = "reservation"
    TRANSPORT = "transport"
    ACCESSIBILITY = "accessibility"
    VISITOR_NOTICE = "visitor_notice"
    GENERAL_DESCRIPTION = "general_description"
