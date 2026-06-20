import json
from typing import Any

from app.config import get_settings


class LLMClient:
    """Anthropic wrapper with deterministic mock fallback for offline MVP runs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self._should_use_anthropic():
            try:
                import anthropic

                api_key = self.settings.llm_api_key()
                if api_key:
                    self._client = anthropic.Anthropic(
                        api_key=api_key,
                        base_url=self.settings.anthropic_base_url,
                    )
            except Exception:
                self._client = None

    def _should_use_anthropic(self) -> bool:
        if self.settings.llm_mode == "mock":
            return False
        return bool(self.settings.llm_api_key())

    async def complete(self, system: str, user: str, max_tokens: int = 1200) -> str:
        if self._client:
            message = self._client.messages.create(
                model=self.settings.llm_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = [block.text for block in message.content if hasattr(block, "text")]
            return "\n".join(parts)
        return self._mock_complete(system, user)

    def _mock_complete(self, system: str, user: str) -> str:
        if "intent" in system.lower() or "parse" in system.lower():
            return json.dumps(self._mock_intent(user), ensure_ascii=False)
        if "compose" in system.lower() or "answer" in system.lower():
            return user
        return user

    def _mock_intent(self, user: str) -> dict[str, Any]:
        from app.agents.intent_agent import IntentAgent

        return IntentAgent.parse_deterministic(user)
