from pydantic import BaseModel


class PlaceContext(BaseModel):
    original_name: str
    canonical_name: str
    country: str | None = None
    city: str | None = None
    confidence: float = 0.9
    source: str = "query_understanding"
