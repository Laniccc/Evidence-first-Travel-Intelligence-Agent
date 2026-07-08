from app.tools.mock import data as mock_catalog


def resolve_start_location(start_location: str) -> tuple[str, str, str] | None:
    for alias, (country, city, loc) in mock_catalog.LOCATION_ALIASES.items():
        if start_location.lower() in {alias.lower(), alias}:
            return country, city, loc
    return None


def resolve_city_country_from_text(text: str) -> tuple[str, str] | None:
    lower = text.lower()
    for key, (country, city) in mock_catalog.CITY_COUNTRY.items():
        if key in lower:
            return country, city
    return None


def iter_location_aliases():
    return mock_catalog.LOCATION_ALIASES.items()


def iter_city_country():
    return mock_catalog.CITY_COUNTRY.items()
