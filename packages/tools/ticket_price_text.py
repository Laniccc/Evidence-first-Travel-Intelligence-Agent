"""Shared text heuristics for ticket price extraction."""

from __future__ import annotations

import re

_PRICE_CONTEXT = (
    r"门票|票价|成人票|儿童票|学生票|老人票|老年票|优待票|优惠票|"
    r"景区票|入园票|进山票|普通票|套票|联票|区间车|观光车|船票|游船|"
    r"索道|缆车|收费|售价|价格|购票|预约票|ticket|admission|entrance|fare|price"
)
_AMOUNT = r"\d{1,4}(?:,\d{3})*(?:\.\d+)?"
_CURRENCY = r"元|块|RMB|CNY|日元|JPY|円|韩元|KRW|₩"

_PREFIX_PRICE_RE = re.compile(rf"[¥￥]\s*{_AMOUNT}(?:\s*(?:起|/人|每人|人))?", re.I)
_AMOUNT_PRICE_RE = re.compile(
    rf"{_AMOUNT}\s*(?:{_CURRENCY})(?:\s*(?:起|/人|每人|人))?",
    re.I,
)
_EXPLICIT_PRICE_RE = re.compile(
    rf"(?:(?:{_PRICE_CONTEXT})[^。；;\n]{{0,40}}(?:{_PREFIX_PRICE_RE.pattern}|{_AMOUNT_PRICE_RE.pattern}))|"
    rf"(?:(?:{_PREFIX_PRICE_RE.pattern}|{_AMOUNT_PRICE_RE.pattern})[^。；;\n]{{0,32}}(?:{_PRICE_CONTEXT}|/人|每人|起))",
    re.I,
)
_FREE_PRICE_RE = re.compile(
    rf"(?:(?:{_PRICE_CONTEXT})[^。；;\n]{{0,32}}(?:免费|免票|免门票|无需门票|free|(?<!\d)0\s*元))|"
    rf"(?:(?:免费|免票|免门票|无需门票|free|(?<!\d)0\s*元)[^。；;\n]{{0,32}}(?:{_PRICE_CONTEXT}|入园|入馆|开放))",
    re.I,
)

_LOGIN_PROMPT_RE = re.compile(r"您好|请\s*登录|登录|登陆|注册|sign\s*in|log\s*in", re.I)
_FREE_TIME_WINDOW_RE = re.compile(
    r"免门票入园时间|免费入园时间|免票时间|免费开放时间|开放时间|"
    r"每日\s*\d{1,2}\s*点前\s*免费开放|"
    r"\d{1,2}:\d{2}[^。；;\n]{0,40}免费开放|"
    r"免费开放[^。；;\n]{0,20}(时间|时段)",
    re.I,
)
_FREE_BOOKING_NOISE_RE = re.compile(r"抢票|预约数量|每日\s*\d+\s*张|约满|酒店|机票|火车|汽车", re.I)
_COUNT_OR_RATING_RE = re.compile(r"点评|评论|浏览|关注|评分|分\(|/5|条|张|人次|销量", re.I)
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")


def _bad_numeric_context(mention: str) -> bool:
    if _TIME_RE.search(mention):
        without_price = _AMOUNT_PRICE_RE.sub("", mention)
        without_price = _PREFIX_PRICE_RE.sub("", without_price)
        if _TIME_RE.search(without_price):
            return True
    return bool(_COUNT_OR_RATING_RE.search(mention))


def _usable_free_policy_match(match: re.Match[str] | None, context: str | None = None) -> bool:
    if not match:
        return False
    mention = match.group(0)
    window = context if context is not None else mention
    time_range_free_open = re.compile(
        r"\d{1,2}[:\uff1a]\d{2}\s*[-\u2013\u2014~\uff5e]\s*\d{1,2}[:\uff1a]\d{2}"
        r"[^\n;\uff1b\u3002]{0,32}(?:\u514d\u8d39\u5f00\u653e|\u514d\u8d39\u53c2\u89c2)",
        re.I,
    )
    free_open_hour_context = re.compile(
        r"(?:\u5f00\u653e\u65f6\u95f4|\u8425\u4e1a\u65f6\u95f4|\u5165\u56ed\u65f6\u95f4)"
        r"[^\n;\uff1b\u3002]{0,48}(?:\u514d\u8d39\u5f00\u653e|\u514d\u8d39\u53c2\u89c2)",
        re.I,
    )
    limited_free_policy = re.compile(
        r"(?:\u672a\u6ee1|\u513f\u7ae5|\u8001\u4eba|\u8001\u5e74|\u5b66\u751f|\u519b\u4eba|"
        r"\u6b8b\u75be|\u6d88\u9632|\u4f18\u60e0|\u534a\u4ef7|\u653f\u7b56|\u987b\u9884\u7ea6|"
        r"\u4e2d\u56fd\u516c\u6c11|\u672a\u6210\u5e74|\u79bb\u4f11|\u8eab\u9ad8|\u5468\u5c81|"
        r"\u514d\u8d39\u53c2\u89c2)",
        re.I,
    )
    general_free_admission = re.compile(
        r"(?:\u95e8\u7968|\u5165\u56ed|\u5165\u9986|admission|entrance)[^\n;\uff1b\u3002]{0,24}"
        r"(?:\u514d\u8d39|\u514d\u7968|\u65e0\u9700\u95e8\u7968)|"
        r"(?:\u514d\u8d39|\u514d\u7968|\u65e0\u9700\u95e8\u7968)[^\n;\uff1b\u3002]{0,24}"
        r"(?:\u95e8\u7968|\u5165\u56ed|\u5165\u9986|admission|entrance)",
        re.I,
    )
    if _LOGIN_PROMPT_RE.search(mention):
        return False
    if _FREE_TIME_WINDOW_RE.search(window):
        return False
    if time_range_free_open.search(window):
        return False
    if free_open_hour_context.search(window):
        return False
    if _FREE_BOOKING_NOISE_RE.search(window):
        return False
    if (
        re.search(r"\u514d\u8d39(?:\u5f00\u653e|\u53c2\u89c2)", window)
        and not general_free_admission.search(window)
    ):
        return False
    if limited_free_policy.search(window) and not general_free_admission.search(window):
        return False
    return True


def has_explicit_ticket_price_signal(text: str) -> bool:
    """Return True only when text contains a concrete ticket price or free policy."""
    return first_ticket_price_mention(text) is not None


def first_ticket_price_mention(text: str) -> str | None:
    """Return the first concrete ticket price phrase, excluding counts and ratings."""
    blob = str(text or "").strip()
    if not blob:
        return None
    for price_match in _EXPLICIT_PRICE_RE.finditer(blob):
        mention = price_match.group(0).strip()
        if _LOGIN_PROMPT_RE.search(mention):
            continue
        if _bad_numeric_context(mention):
            continue
        return mention
    free_match = _FREE_PRICE_RE.search(blob)
    if free_match:
        context = blob[max(0, free_match.start() - 20) : free_match.end() + 48]
    else:
        context = None
    if _usable_free_policy_match(free_match, context):
        return free_match.group(0).strip()
    return None


def first_ticket_price_amount(text: str) -> float | None:
    """Extract the first numeric amount from text already known to describe ticket pricing."""
    mention = first_ticket_price_mention(text)
    if not mention:
        return None
    if _usable_free_policy_match(_FREE_PRICE_RE.search(mention)):
        return 0.0
    match = _PREFIX_PRICE_RE.search(mention) or _AMOUNT_PRICE_RE.search(mention)
    if not match:
        return None
    amount_match = re.search(_AMOUNT, match.group(0))
    if not amount_match:
        return None
    try:
        return float(amount_match.group(0).replace(",", ""))
    except ValueError:
        return None
