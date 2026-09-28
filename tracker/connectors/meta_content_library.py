"""Placeholder for the Meta Content Library API connector.

Meta Content Library (the successor of CrowdTangle) is available to approved
researchers. Once access is granted, implement the `Connector` methods here
using its search endpoints (keyword search over public page/group posts,
page lookups). Nothing else in the system needs to change.

This project intentionally does NOT scrape Facebook: scraping violates Meta's
terms, gets accounts banned and exposes the analyst to legal risk.
"""

from __future__ import annotations

from ..models import Page, Post
from .base import Connector


class MetaContentLibraryConnector(Connector):
    name = "Meta Content Library"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _todo(self):
        raise NotImplementedError(
            "Meta Content Library connector is not implemented yet. "
            "Apply for access at https://transparency.meta.com/researchtools/meta-content-library"
        )

    def get_post(self, post_id_or_url: str) -> Post | None:
        self._todo()

    def get_page(self, page_id: str) -> Page | None:
        self._todo()

    def posts_by_page(self, page_id: str) -> list[Post]:
        self._todo()

    def posts_with_link(self, canonical_link: str) -> list[Post]:
        self._todo()

    def posts_with_image(self, phash: str, max_distance: int) -> list[Post]:
        self._todo()

    def posts_with_similar_text(self, text: str, min_similarity: float) -> list[Post]:
        self._todo()
