"""One model request per normalize call; UnderstandingHandler owns the retry budget."""

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from app.context.conversation_context import ConversationContext
from app.understanding.normalized_user_request import NormalizedUserRequest
from app.understanding.task_request import TaskRequest, to_normalized_request


class TaskModel(Protocol):
    async def complete(self, *, system: str, user: str, max_tokens: int) -> str: ...


class PrimaryUnderstandingAdapter:
    def __init__(self, model: TaskModel, *, max_tokens: int = 1536,
                 clock: Callable[[], datetime] | None = None,
                 request_timezone: str = "Asia/Shanghai") -> None:
        if not 128 <= max_tokens <= 4096:
            raise ValueError("understanding token budget out of bounds")
        ZoneInfo(request_timezone)
        self._model = model
        self._max_tokens = max_tokens
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timezone = request_timezone
        prompt = (Path(__file__).parent / "prompts" / "task_request.system.md").read_text(encoding="utf-8")
        schema = json.dumps(TaskRequest.model_json_schema(), sort_keys=True, ensure_ascii=False)
        self._system = prompt + "\nSchema:\n" + schema
        self.audit_versions = {
            "model": str(getattr(model, "model", "injected"))[:100],
            "prompt": sha256(prompt.encode()).hexdigest(),
            "schema": sha256(schema.encode()).hexdigest(),
        }

    async def normalize(self, raw_query: str, conversation_context: ConversationContext,
                        *, repair: bool = False) -> NormalizedUserRequest:
        if not raw_query.strip() or len(raw_query) > 4000:
            raise ValueError("understanding input out of bounds")
        names = []
        for place in conversation_context.last_places[:2]:
            if isinstance(place, str):
                name = place
            elif isinstance(place, dict):
                name = place.get("canonical_name") or place.get("name") or place.get("mention")
            else:
                name = getattr(place, "canonical_name", None) or getattr(place, "name", None)
            if isinstance(name, str):
                names.append(name[:200])
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("reference clock requires timezone")
        user = json.dumps({
            "query": raw_query, "repair": repair,
            "reference_time": now.isoformat(), "request_timezone": self._timezone,
            "conversation": {
                "last_places": names,
                "last_travel_date": (conversation_context.last_travel_date or "")[:100],
                "confirmed_preferences": [str(p)[:300] for p in conversation_context.confirmed_preferences[:12]],
            },
        }, ensure_ascii=False)
        text = await self._model.complete(system=self._system, user=user, max_tokens=self._max_tokens)
        if len(text) > 32000:
            raise ValueError("llm_schema_invalid")
        task = TaskRequest.model_validate_json(text)
        return to_normalized_request(task, raw_query=raw_query)
