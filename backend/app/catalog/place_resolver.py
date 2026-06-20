import logging
from abc import ABC, abstractmethod

from app.agents.place_entity_extractor import GEO_CITY_ALIASES, LLMPlaceEntityExtractor, PlaceMention
from app.catalog.place_catalog import get_place_catalog
from app.config import get_settings
from app.schemas.conversation_context import ConversationContext
from app.schemas.place_candidate import PlaceCandidate, PlaceResolutionSource
from app.storage.place_cache import PlaceCache

logger = logging.getLogger(__name__)


class BasePlaceResolver(ABC):
    name: str = "base"

    @abstractmethod
    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        pass


class SessionMemoryResolver(BasePlaceResolver):
    name = "session_memory"

    def __init__(self, context: ConversationContext | None) -> None:
        self.context = context

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        ctx = context or self.context
        if not ctx:
            return None
        if mention.entity_type == "poi" and ctx.last_places:
            for pc in reversed(ctx.last_places):
                if mention.text in pc.canonical_name or pc.canonical_name in mention.text:
                    return PlaceCandidate(
                        mention=mention.text,
                        canonical_name=pc.canonical_name,
                        country=pc.country,
                        city=pc.city,
                        place_type="poi",
                        confidence=0.85,
                        resolution_source=PlaceResolutionSource.SESSION_MEMORY,
                    )
        if mention.entity_type == "city" and ctx.last_city:
            if mention.city == ctx.last_city or mention.text in {ctx.last_city, ctx.last_country or ""}:
                return PlaceCandidate(
                    mention=mention.text,
                    canonical_name=ctx.last_city,
                    country=ctx.last_country,
                    city=ctx.last_city,
                    place_type="city",
                    confidence=0.8,
                    resolution_source=PlaceResolutionSource.SESSION_MEMORY,
                )
        return None


class LocalPlaceCacheResolver(BasePlaceResolver):
    name = "local_cache"

    def __init__(self, cache: PlaceCache | None = None) -> None:
        self.cache = cache or PlaceCache()

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        key = PlaceCache.cache_key(mention.text, mention.country, mention.city)
        hit = self.cache.get(key)
        if hit and PlaceResolver._should_cache(hit):
            return hit.model_copy(update={"resolution_source": PlaceResolutionSource.LOCAL_CACHE})
        return None


class RealPlacesResolver(BasePlaceResolver):
    name = "real_places"

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        if mention.entity_type not in {"poi", "place"}:
            return None
        settings = get_settings()
        if not settings.enable_real_places:
            return None
        try:
            from app.tools.real.places_tool import RealPlacesTool

            tool = RealPlacesTool()
            if not tool.is_available():
                return None
            await tool.run(
                place_name=mention.text,
                country=mention.country,
                city=mention.city,
            )
            return PlaceCandidate(
                mention=mention.text,
                canonical_name=mention.text,
                country=mention.country,
                city=mention.city,
                place_type="poi",
                confidence=0.78,
                resolution_source=PlaceResolutionSource.REAL_PLACES,
            )
        except Exception as exc:
            logger.debug("RealPlacesResolver skip: %s", exc)
            return None


class MCPPlacesResolver(BasePlaceResolver):
    name = "mcp_places"

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        settings = get_settings()
        if not settings.mcp_enabled or mention.entity_type not in {"poi", "place"}:
            return None
        return PlaceCandidate(
            mention=mention.text,
            canonical_name=mention.text,
            country=mention.country,
            city=mention.city,
            place_type="poi",
            confidence=0.7,
            resolution_source=PlaceResolutionSource.MCP_PLACES,
            metadata={"stub": True},
        )


class LLMGeocodeResolver(BasePlaceResolver):
    name = "llm_geocode"

    def __init__(self, llm_client=None) -> None:
        self.extractor = LLMPlaceEntityExtractor(llm_client)

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        if mention.entity_type in {"poi", "place"}:
            return None
        country = mention.country
        city = mention.city
        if not country or not city:
            for alias, (c_country, c_city) in GEO_CITY_ALIASES.items():
                if alias in mention.text or alias.lower() in mention.text.lower():
                    country, city = c_country, c_city
                    break
        if mention.entity_type == "city" and city and country:
            return PlaceCandidate(
                mention=mention.text,
                canonical_name=city,
                country=country,
                city=city,
                place_type="city",
                confidence=max(mention.confidence, 0.82),
                resolution_source=PlaceResolutionSource.LLM_GEocode,
            )
        if country and not city:
            return PlaceCandidate(
                mention=mention.text,
                canonical_name=country,
                country=country,
                place_type="country",
                confidence=mention.confidence,
                resolution_source=PlaceResolutionSource.LLM_GEocode,
            )
        return None


class MockCatalogResolver(BasePlaceResolver):
    """Fallback only — mock POI registry, not primary geocoding."""

    name = "mock_catalog"

    async def resolve(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        if mention.entity_type not in {"poi", "place"}:
            return None
        catalog = get_place_catalog()
        hits = catalog.find_places_in_text(mention.text)
        if not hits:
            return None
        canonical = hits[0]
        ctx = catalog.resolve_place_context(canonical)
        return PlaceCandidate(
            mention=mention.text,
            canonical_name=canonical,
            country=ctx.country,
            city=ctx.city,
            place_type="poi",
            confidence=0.55,
            resolution_source=PlaceResolutionSource.MOCK_CATALOG,
            metadata={"fallback": True},
        )


class PlaceResolver:
    """Chain resolver: memory → cache → real → mcp → geocode → mock catalog."""

    def __init__(
        self,
        llm_client=None,
        conversation_context: ConversationContext | None = None,
        cache: PlaceCache | None = None,
    ) -> None:
        self.cache = cache or PlaceCache()
        self.extractor = LLMPlaceEntityExtractor(llm_client)
        self.resolvers: list[BasePlaceResolver] = [
            SessionMemoryResolver(conversation_context),
            LocalPlaceCacheResolver(self.cache),
            RealPlacesResolver(),
            MCPPlacesResolver(),
            LLMGeocodeResolver(llm_client),
            MockCatalogResolver(),
        ]

    async def resolve(
        self,
        raw_query: str,
        mentions: list[PlaceMention] | None = None,
        context: ConversationContext | None = None,
    ) -> list[PlaceCandidate]:
        extracted = mentions if mentions is not None else await self.extractor.extract(raw_query, context)
        if not extracted:
            extracted = LLMPlaceEntityExtractor.extract_sync(raw_query, context)

        results: list[PlaceCandidate] = []
        for mention in extracted:
            candidate = await self._resolve_one(raw_query, mention, context)
            if candidate:
                results.append(candidate)
                if self._should_cache(candidate):
                    key = PlaceCache.cache_key(mention.text, mention.country, mention.city)
                    self.cache.set(key, candidate)
        return results

    @staticmethod
    def _should_cache(candidate: PlaceCandidate) -> bool:
        if candidate.resolution_source == PlaceResolutionSource.EXTRACTOR:
            return False
        if candidate.is_poi and candidate.canonical_name == candidate.mention:
            return candidate.resolution_source == PlaceResolutionSource.MOCK_CATALOG
        return True

    async def _resolve_one(
        self,
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
    ) -> PlaceCandidate | None:
        for resolver in self.resolvers:
            try:
                hit = await resolver.resolve(raw_query, mention, context)
            except Exception as exc:
                logger.debug("%s failed: %s", resolver.name, exc)
                continue
            if hit:
                return hit
        return PlaceCandidate(
            mention=mention.text,
            canonical_name=mention.city if mention.entity_type == "city" else mention.text,
            country=mention.country,
            city=mention.city,
            place_type=mention.entity_type,
            confidence=mention.confidence * 0.5,
            resolution_source=PlaceResolutionSource.EXTRACTOR,
            metadata={"unresolved": True},
        )

    @classmethod
    def resolve_sync(
        cls,
        raw_query: str,
        context: ConversationContext | None = None,
        llm_client=None,
    ) -> list[PlaceCandidate]:
        mentions = LLMPlaceEntityExtractor.extract_sync(raw_query, context)
        cache = PlaceCache()
        sync_resolvers: list[BasePlaceResolver] = [
            SessionMemoryResolver(context),
            LocalPlaceCacheResolver(cache),
            LLMGeocodeResolver(llm_client),
            MockCatalogResolver(),
        ]
        results: list[PlaceCandidate] = []
        for mention in mentions:
            hit = None
            for resolver in sync_resolvers:
                hit = cls._resolve_inline(raw_query, mention, context, resolver, cache)
                if hit:
                    break
            if not hit:
                hit = PlaceCandidate(
                    mention=mention.text,
                    canonical_name=mention.city if mention.entity_type == "city" else mention.text,
                    country=mention.country,
                    city=mention.city,
                    place_type=mention.entity_type,
                    confidence=mention.confidence,
                    resolution_source=PlaceResolutionSource.EXTRACTOR,
                )
            results.append(hit)
            if cls._should_cache(hit):
                cache.set(PlaceCache.cache_key(mention.text, mention.country, mention.city), hit)
        return results

    @staticmethod
    def _resolve_inline(
        raw_query: str,
        mention: PlaceMention,
        context: ConversationContext | None,
        resolver: BasePlaceResolver,
        cache: PlaceCache,
    ) -> PlaceCandidate | None:
        if isinstance(resolver, SessionMemoryResolver):
            ctx = context
            if ctx and mention.entity_type == "city" and ctx.last_city:
                return PlaceCandidate(
                    mention=mention.text,
                    canonical_name=ctx.last_city,
                    country=ctx.last_country,
                    city=ctx.last_city,
                    place_type="city",
                    confidence=0.8,
                    resolution_source=PlaceResolutionSource.SESSION_MEMORY,
                )
        if isinstance(resolver, LocalPlaceCacheResolver):
            key = PlaceCache.cache_key(mention.text, mention.country, mention.city)
            hit = cache.get(key)
            if hit and PlaceResolver._should_cache(hit):
                return hit.model_copy(update={"resolution_source": PlaceResolutionSource.LOCAL_CACHE})
            return None
        if isinstance(resolver, LLMGeocodeResolver):
            if mention.entity_type in {"poi", "place"}:
                return None
            country, city = mention.country, mention.city
            if not country or not city:
                for alias, (c_country, c_city) in GEO_CITY_ALIASES.items():
                    if alias in mention.text or alias.lower() in mention.text.lower():
                        country, city = c_country, c_city
                        break
            if mention.entity_type == "city" and city and country:
                return PlaceCandidate(
                    mention=mention.text,
                    canonical_name=city,
                    country=country,
                    city=city,
                    place_type="city",
                    confidence=max(mention.confidence, 0.82),
                    resolution_source=PlaceResolutionSource.LLM_GEocode,
                )
        if isinstance(resolver, MockCatalogResolver):
            catalog = get_place_catalog()
            hits = catalog.find_places_in_text(mention.text)
            if hits:
                ctx = catalog.resolve_place_context(hits[0])
                return PlaceCandidate(
                    mention=mention.text,
                    canonical_name=hits[0],
                    country=ctx.country,
                    city=ctx.city,
                    place_type="poi",
                    confidence=0.55,
                    resolution_source=PlaceResolutionSource.MOCK_CATALOG,
                )
        return None


async def resolve_places_for_query(
    raw_query: str,
    context: ConversationContext | None = None,
    llm_client=None,
) -> list[PlaceCandidate]:
    resolver = PlaceResolver(llm_client=llm_client, conversation_context=context)
    return await resolver.resolve(raw_query, context=context)
