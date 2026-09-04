"""Conservative date resolution; ambiguous dates become clarification, never today."""

from datetime import UTC, date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from app.understanding.normalized_user_request import NormalizedUserRequest

_ISO_DATE = re.compile(
    r"(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_CHINESE_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日?")


def _localize(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(UTC)
    local = value.replace(tzinfo=zone)
    if local.utcoffset() != value.replace(tzinfo=zone, fold=1).utcoffset():
        raise ValueError("ambiguous or nonexistent local time")
    if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != value:
        raise ValueError("nonexistent local time")
    return local.astimezone(UTC)


def _parse(value: str, zone: ZoneInfo) -> datetime:
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        year, month, day = (int(v) for v in value.split("-"))
        return _localize(datetime.combine(date(year, month, day), time()), zone)
    if not re.fullmatch(_ISO_DATE, value):
        raise ValueError("explicit ISO date required")
    return _localize(datetime.fromisoformat(value.replace("Z", "+00:00")), zone)


def resolve_as_of(request: NormalizedUserRequest, *, now: datetime,
                  request_timezone: str) -> tuple[datetime, bool]:
    zone = ZoneInfo(request_timezone)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must have a timezone")
    raw = request.raw_query
    tokens = _ISO_DATE.findall(raw)
    tokens.extend(f"{y}-{m}-{d}" for y, m, d in _CHINESE_DATE.findall(raw))
    raw_dates = [_parse(token, zone) for token in tokens]
    local_today = now.astimezone(zone).date()
    for word, offset in (("今天", 0), ("明天", 1), ("后天", 2), ("昨天", -1)):
        if word in raw and not (word == "后天" and "大后天" in raw):
            raw_dates.append(_localize(datetime.combine(local_today + timedelta(days=offset), time()), zone))
    if len(set(raw_dates)) > 1:
        raise ValueError("multiple dates require clarification")
    reference = request.time_scope.reference_date
    if reference:
        resolved = _parse(reference, zone)
        if raw_dates and resolved.astimezone(zone).date() != raw_dates[0].astimezone(zone).date():
            raise ValueError("model date conflicts with user date")
    elif raw_dates:
        resolved = raw_dates[0]
    else:
        if request.time_scope.scope == "specific_date" or re.search(
            r"\d{1,2}月\d{1,2}日?|\d{4}/\d|下周|下个|下月|下个月|本周|这周|周末|大后天|前天", raw
        ):
            raise ValueError("date requires clarification")
        return now.astimezone(UTC), False
    # An observed current snapshot is not proof for another requested instant.
    return resolved, resolved != now.astimezone(UTC)
