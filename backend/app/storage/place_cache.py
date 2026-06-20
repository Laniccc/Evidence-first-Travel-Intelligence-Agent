import json
import logging
from pathlib import Path

from app.schemas.place_candidate import PlaceCandidate

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "place_resolver_cache.json"


class PlaceCache:
    """In-memory + optional file-backed cache for PlaceResolver."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _DEFAULT_CACHE_PATH
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("PlaceCache load failed: %s", exc)
            self._data = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("PlaceCache save failed: %s", exc)

    @staticmethod
    def cache_key(mention: str, country: str | None = None, city: str | None = None) -> str:
        parts = [mention.strip().lower()]
        if city:
            parts.append(city.lower())
        if country:
            parts.append(country.lower())
        return "|".join(parts)

    def get(self, key: str) -> PlaceCandidate | None:
        raw = self._data.get(key)
        if not raw:
            return None
        return PlaceCandidate.model_validate(raw)

    def set(self, key: str, candidate: PlaceCandidate) -> None:
        self._data[key] = candidate.model_dump()
        self._save()
