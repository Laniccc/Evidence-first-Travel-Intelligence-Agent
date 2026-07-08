from pydantic import BaseModel, Field


class PlaceInfo(BaseModel):
    name: str
    name_local: str | None = None
    country: str
    city: str
    address: str | None = None
    category: str | None = None
    description: str | None = None
    coordinates: dict | None = None
