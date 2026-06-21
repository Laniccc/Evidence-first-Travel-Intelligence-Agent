from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.tool_gateway.config import ToolGatewayConfig


class JavaToolGatewayError(Exception):
    pass


class JavaToolGatewayUnavailable(JavaToolGatewayError):
    pass


class JavaToolGatewayClient:
    def __init__(self, config: ToolGatewayConfig, timeout_seconds: float = 30.0) -> None:
        self._config = config
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return self._config.use_java_tool_gateway

    def call_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.base_url}/internal/tools/call"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail) if detail else {}
            except json.JSONDecodeError:
                parsed = {"error": detail or exc.reason}
            if exc.code >= 500:
                raise JavaToolGatewayUnavailable(parsed.get("error") or exc.reason) from exc
            return parsed
        except urllib.error.URLError as exc:
            raise JavaToolGatewayUnavailable(str(exc.reason)) from exc
