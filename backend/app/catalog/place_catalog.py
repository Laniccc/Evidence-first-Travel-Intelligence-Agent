from functools import lru_cache

from app.schemas.place_context import PlaceContext
from app.tools.mock import data as mock_catalog


class PlaceLocation:
    def __init__(self, country: str, city: str) -> None:
        self.country = country
        self.city = city


class MockPlaceCatalogBackend:
    def normalize_place_name(self, name: str) -> str | None:
        return mock_catalog.normalize_place_name(name)

    def get_place_location(self, place_name: str) -> PlaceLocation | None:
        loc = mock_catalog.get_place_location(place_name)
        if not loc:
            return None
        return PlaceLocation(country=loc[0], city=loc[1])

    def is_registered(self, place_name: str) -> bool:
        canonical = self.normalize_place_name(place_name) or place_name
        return canonical in mock_catalog.PLACE_REGISTRY

    def registered_places_for_city(self, country: str, city: str) -> list[str]:
        return mock_catalog.registered_places_for_city(country, city)

    def registered_places_for_country(self, country: str) -> list[str]:
        return mock_catalog.registered_places_for_country(country)

    def find_places_in_text(self, text: str) -> list[str]:
        return mock_catalog.find_places_in_text(text)


class PlaceCatalogService:
    def __init__(self, backend: MockPlaceCatalogBackend | None = None) -> None:
        self._backend = backend or MockPlaceCatalogBackend()

    def normalize_place_name(self, name: str) -> str | None:
        return self._backend.normalize_place_name(name)

    def get_place_location(self, place_name: str) -> PlaceLocation | None:
        return self._backend.get_place_location(place_name)

    def is_registered(self, place_name: str) -> bool:
        return self._backend.is_registered(place_name)

    def registered_places_for_city(self, country: str, city: str) -> list[str]:
        return self._backend.registered_places_for_city(country, city)

    def registered_places_for_country(self, country: str) -> list[str]:
        return self._backend.registered_places_for_country(country)

    def find_places_in_text(self, text: str) -> list[str]:
        return self._backend.find_places_in_text(text)

    def resolve_place_context(self, original_name: str) -> PlaceContext:
        canonical = self.normalize_place_name(original_name) or original_name
        loc = self.get_place_location(canonical)
        return PlaceContext(
            original_name=original_name,
            canonical_name=canonical,
            country=loc.country if loc else None,
            city=loc.city if loc else None,
            confidence=0.95 if loc else 0.5,
            source="catalog",
        )


@lru_cache
def get_place_catalog() -> PlaceCatalogService:
    return PlaceCatalogService()
