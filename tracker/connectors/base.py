"""Connector interface.

Every data source (CSV exports, manual entry, Meta Content Library, ...)
implements the same small set of lookups. The expansion engine only talks to
this interface, so a new source can be plugged in without touching the rest
of the system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Domain, Page, Post


class Connector(ABC):
    name: str = "connector"

    @abstractmethod
    def get_post(self, post_id_or_url: str) -> Post | None:
        """Resolve a post by id or by its permalink."""

    @abstractmethod
    def get_page(self, page_id: str) -> Page | None: ...

    @abstractmethod
    def posts_by_page(self, page_id: str) -> list[Post]: ...

    @abstractmethod
    def posts_with_link(self, canonical_link: str) -> list[Post]:
        """Posts that shared the given (canonicalized) external link."""

    @abstractmethod
    def posts_with_image(self, phash: str, max_distance: int) -> list[Post]:
        """Posts whose image perceptual hash is within `max_distance` bits."""

    @abstractmethod
    def posts_with_similar_text(self, text: str, min_similarity: float) -> list[Post]:
        """Posts whose text is a near-duplicate of `text`."""

    def get_domain(self, domain: str) -> Domain | None:
        return None

    def domains_with_tracking_id(self, tracking_id: str) -> list[Domain]:
        return []

    def all_pages(self) -> list[Page]:
        """Pages known to the source (used to populate UI pickers)."""
        return []
