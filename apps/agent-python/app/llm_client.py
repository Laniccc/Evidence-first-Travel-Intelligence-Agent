from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_JSON_ONLY_SUFFIX = (
    "\n\nOutput ONLY the requested JSON object. "
    "Do not include markdown fences, explanations, or chain-of-thought."
)


class LLMClient:
    """Anthropic-compatible LLM client (DeepSeek / Anthropic API). Requires network + API key."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        api_key = self.settings.llm_api_key()
        if not api_key:
            raise RuntimeError(
                "LLM API key required: set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY in apps/agent-python/.env"
            )
        try:
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=api_key,
                base_url=self.settings.anthropic_base_url,
                timeout=self.settings.llm_request_timeout_seconds,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize LLM client: {exc}") from exc

    def _should_use_anthropic(self) -> bool:
        return self._client is not None

    def _uses_deepseek_anthropic(self) -> bool:
        base = (self.settings.anthropic_base_url or "").lower()
        return "deepseek.com" in base

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1200,
        *,
        json_only: bool = False,
    ) -> str:
        if not self._client:
            raise RuntimeError("LLM client not initialized; API key is required.")
        retries = max(1, int(self.settings.llm_empty_response_retries))
        token_budget = max_tokens
        if json_only:
            token_budget = max(token_budget, int(self.settings.llm_json_min_tokens))
        last_error: RuntimeError | None = None

        for attempt in range(retries):
            system_prompt = system
            if json_only:
                system_prompt = system + _JSON_ONLY_SUFFIX
            try:
                message = await asyncio.to_thread(
                    self._create_message,
                    system_prompt,
                    user,
                    token_budget,
                )
            except Exception as exc:
                last_error = RuntimeError(f"LLM request failed: {exc}")
                logger.warning("LLM request error (attempt %s/%s): %s", attempt + 1, retries, exc)
                token_budget = min(token_budget * 2, self.settings.llm_max_output_tokens)
                continue

            text, stop_reason, block_types = self._extract_message_text(message)
            truncated = stop_reason == "max_tokens" or block_types == ["thinking"]
            ceiling = int(self.settings.llm_max_output_tokens)

            if text and not truncated:
                return text

            if text and truncated:
                if token_budget >= ceiling:
                    logger.warning(
                        "LLM output still truncated at token ceiling %s (%s chars); returning partial",
                        ceiling,
                        len(text),
                    )
                    return text
                logger.warning(
                    "LLM output truncated (stop_reason=%s, %s chars, budget=%s); retrying with higher max_tokens",
                    stop_reason,
                    len(text),
                    token_budget,
                )
                token_budget = min(
                    max(token_budget * 2, int(self.settings.llm_json_min_tokens)),
                    ceiling,
                )
                last_error = RuntimeError(
                    f"LLM output truncated (stop_reason={stop_reason}, budget={token_budget})"
                )
                await asyncio.sleep(0.4 * (attempt + 1))
                continue

            usage = getattr(message, "usage", None)
            logger.warning(
                "LLM returned no text (attempt %s/%s) stop_reason=%s blocks=%s usage=%s",
                attempt + 1,
                retries,
                stop_reason,
                block_types,
                usage,
            )
            last_error = RuntimeError(
                f"LLM returned empty response (stop_reason={stop_reason}, blocks={block_types})"
            )
            if truncated:
                token_budget = min(
                    max(token_budget * 2, int(self.settings.llm_json_min_tokens)),
                    ceiling,
                )
            await asyncio.sleep(0.4 * (attempt + 1))

        raise last_error or RuntimeError("LLM returned empty response")

    def _create_message(self, system: str, user: str, max_tokens: int) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model(),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self._uses_deepseek_anthropic() and self.settings.llm_disable_thinking:
            kwargs["thinking"] = {"type": "disabled"}
        return self._client.messages.create(**kwargs)

    @staticmethod
    def _extract_message_text(message: Any) -> tuple[str, str | None, list[str]]:
        text_parts: list[str] = []
        block_types: list[str] = []

        for block in message.content or []:
            block_type = getattr(block, "type", None) or type(block).__name__
            block_types.append(str(block_type))
            if block_type == "text" and hasattr(block, "text"):
                if block.text:
                    text_parts.append(block.text)
            elif hasattr(block, "text") and getattr(block, "text", None):
                text_parts.append(str(block.text))

        text = "\n".join(text_parts).strip()
        stop_reason = getattr(message, "stop_reason", None)
        return text, stop_reason, block_types
