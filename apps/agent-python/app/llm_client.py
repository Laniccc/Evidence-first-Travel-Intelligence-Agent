from app.config import get_settings


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
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize LLM client: {exc}") from exc

    def _should_use_anthropic(self) -> bool:
        return self._client is not None

    async def complete(self, system: str, user: str, max_tokens: int = 1200) -> str:
        if not self._client:
            raise RuntimeError("LLM client not initialized; API key is required.")
        message = self._client.messages.create(
            model=self.settings.llm_model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in message.content if hasattr(block, "text")]
        text = "\n".join(parts).strip()
        if not text:
            raise RuntimeError("LLM returned empty response")
        return text
