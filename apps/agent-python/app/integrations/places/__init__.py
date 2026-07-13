"""Places integration facade."""

from app.integrations.places.place_resolver import PlaceResolver, build_place_resolvers

__all__ = [
    "PlaceResolver",
    "build_place_resolvers",
]
