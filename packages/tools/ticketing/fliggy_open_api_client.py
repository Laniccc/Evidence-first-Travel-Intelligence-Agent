"""Taobao Open Platform (TOP) client for Fliggy ticket APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))


class FliggyOpenApiClient:
    """Signed HTTP client for https://gw.api.taobao.com/router/rest."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def gateway_url(self) -> str:
        return (self.settings.fliggy_api_gateway_url or "https://gw.api.taobao.com/router/rest").rstrip("/")

    def _timestamp(self) -> str:
        return datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    def _sign(self, params: dict[str, str], secret: str) -> str:
        items = sorted((k, v) for k, v in params.items() if k != "sign" and v is not None and v != "")
        query = "".join(f"{k}{v}" for k, v in items)
        method = (self.settings.fliggy_api_sign_method or "md5").lower()
        if method == "hmac":
            digest = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.md5).hexdigest()
            return digest.upper()
        base = f"{secret}{query}{secret}"
        return hashlib.md5(base.encode("utf-8")).hexdigest().upper()

    def execute(self, method: str, biz_params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
        app_key = self.settings.fliggy_app_key
        app_secret = self.settings.fliggy_app_secret
        if not app_key or not app_secret:
            return None, "Fliggy Open API not configured (missing app_key or app_secret)"

        params: dict[str, str] = {
            "method": method,
            "app_key": app_key,
            "timestamp": self._timestamp(),
            "format": "json",
            "v": "2.0",
            "sign_method": (self.settings.fliggy_api_sign_method or "md5").lower(),
        }
        session = self.settings.fliggy_session
        if session:
            params["session"] = session
        for key, value in (biz_params or {}).items():
            if value is None or value == "":
                continue
            params[key] = str(value)
        params["sign"] = self._sign(params, app_secret)

        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            self.gateway_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            method="POST",
        )
        timeout = float(self.settings.fliggy_api_timeout_seconds)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = (exc.read() or b"").decode("utf-8", errors="replace")[:500]
            return None, f"Fliggy HTTP {exc.code}: {detail or exc.reason}"
        except Exception as exc:
            return None, str(exc)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, f"Fliggy invalid JSON: {raw[:200]}"

        err = data.get("error_response")
        if err:
            msg = err.get("sub_msg") or err.get("msg") or err.get("sub_code") or "unknown error"
            code = err.get("code", "")
            return None, f"Fliggy API error {code}: {msg}"
        return data, None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _format_price(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return f"¥{value}"
    return str(value)


def scenics_get_response_to_items(response: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    """Map taobao.alitrip.travel.baseinfo.scenics.get JSON to crawler item shape."""
    root = response.get("alitrip_travel_baseinfo_scenics_get_response") or response
    scenic_list = root.get("scenic_list") or {}
    scenics = _as_list(scenic_list.get("scenic_info") or scenic_list.get("scenics") or scenic_list.get("scenic"))

    items: list[dict[str, Any]] = []
    for scenic in scenics:
        if not isinstance(scenic, dict):
            continue
        scenic_id = scenic.get("scenic_id") or scenic.get("ali_scenic_id")
        scenic_name = scenic.get("scenic_name") or scenic.get("name") or scenic.get("scenic")
        products_wrapper = scenic.get("ticket_products") or scenic.get("charge_items") or {}
        products = _as_list(
            products_wrapper.get("ticket_product")
            or products_wrapper.get("charge_item")
            or products_wrapper.get("product")
            or products_wrapper.get("ticket_products")
        )
        if not products:
            items.append(
                {
                    "ticket_type": scenic_name or "景点",
                    "scenic_id": scenic_id,
                    "scenic_name": scenic_name,
                    "booking_channel": "Fliggy",
                    "confidence": 0.5,
                    "source": "fliggy_scenics_get",
                }
            )
        for product in products:
            if not isinstance(product, dict):
                continue
            price = product.get("price") or product.get("min_price") or product.get("sale_price")
            price_text = product.get("price_text") or _format_price(price)
            item_url = (
                product.get("platform_ticket_url")
                or product.get("item_url")
                or product.get("url")
                or product.get("h5_url")
            )
            items.append(
                {
                    "ticket_type": product.get("product_name")
                    or product.get("ticket_type")
                    or product.get("name")
                    or scenic_name,
                    "price": price,
                    "price_text": price_text,
                    "sales_status": product.get("status") or product.get("sales_status") or product.get("sale_status"),
                    "booking_channel": "Fliggy",
                    "platform_ticket_url": item_url,
                    "scenic_id": scenic_id,
                    "scenic_name": scenic_name,
                    "product_id": product.get("product_id") or product.get("item_id") or product.get("ali_product_id"),
                    "confidence": 0.6,
                    "source": "fliggy_scenics_get",
                }
            )
            if len(items) >= max_results:
                return items
        if len(items) >= max_results:
            return items
    return items[:max_results]


def scenic_query_response_to_items(response: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    """Map alitrip.ticket.scenic.query JSON to crawler item shape."""
    root = response.get("alitrip_ticket_scenic_query_response") or response
    ticket_list = root.get("ticket_list") or root.get("ticket_product_list") or {}
    tickets = _as_list(ticket_list.get("ticket") or ticket_list.get("ticket_product") or ticket_list.get("tickets"))

    items: list[dict[str, Any]] = []
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        price = ticket.get("price") or ticket.get("retail_price") or ticket.get("settlement_price")
        items.append(
            {
                "ticket_type": ticket.get("ticket_type") or ticket.get("ticket_name") or ticket.get("name"),
                "price": price,
                "price_text": ticket.get("price_text") or _format_price(price),
                "sales_status": ticket.get("status") or ticket.get("ticket_status"),
                "booking_channel": "Fliggy",
                "platform_ticket_url": ticket.get("url") or ticket.get("item_url"),
                "product_id": ticket.get("item_id") or ticket.get("ali_product_id"),
                "confidence": 0.65,
                "source": "fliggy_ticket_scenic_query",
            }
        )
        if len(items) >= max_results:
            break
    return items
