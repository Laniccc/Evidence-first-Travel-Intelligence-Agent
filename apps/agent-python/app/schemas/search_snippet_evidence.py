"""Metadata for search-snippet evidence in hard-fact chains."""

from __future__ import annotations

from pydantic import BaseModel


class SearchSnippetEvidenceMeta(BaseModel):
    source_type: str = "search_snippet"
    can_discover_url: bool = True
    max_adoption_level: str = "candidate_only"
    requires_page_read_for_strong: bool = True


DEFAULT_SEARCH_SNIPPET_META = SearchSnippetEvidenceMeta()
