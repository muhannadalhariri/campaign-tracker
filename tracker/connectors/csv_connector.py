"""Connector backed by CSV files (manual collection or exports from lawful tools).

posts.csv   (required)  post_id, page_id, created_at, text, permalink, links,
                        image_phash, reactions, shares, page_name
pages.csv   (optional)  page_id, name, created_at, admin_countries,
                        name_changes, followers, category
domains.csv (optional)  domain, tracking_ids, registered_at, registrar

Multi-valued cells (links, admin_countries, tracking_ids) are separated by
"|". Links found inside `text` are picked up automatically.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ..models import Domain, Page, Post
from ..normalize import canonical_url, extract_hashtags, extract_urls, split_multi
from ..similarity import TextIndex, hamming_hex
from .base import Connector

REQUIRED_POST_COLUMNS = {"post_id", "page_id", "created_at"}


def _ts(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts.to_pydatetime()


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


class CSVConnector(Connector):
    name = "CSV"

    def __init__(self, posts, pages=None, domains=None):
        """Each argument is a path, a file-like object or a DataFrame."""
        posts_df = self._read(posts)
        missing = REQUIRED_POST_COLUMNS - set(posts_df.columns)
        if missing:
            raise ValueError(f"posts.csv is missing columns: {', '.join(sorted(missing))}")

        self.posts: dict[str, Post] = {}
        page_names: dict[str, str] = {}
        for row in posts_df.to_dict("records"):
            created = _ts(row.get("created_at"))
            if created is None:
                continue
            text = _str(row.get("text"))
            raw_links = split_multi(row.get("links")) + extract_urls(text)
            links = sorted({canonical_url(u) for u in raw_links if u})
            post = Post(
                post_id=_str(row["post_id"]),
                page_id=_str(row["page_id"]),
                created_at=created,
                text=text,
                permalink=_str(row.get("permalink")),
                links=links,
                image_phash=_str(row.get("image_phash")).lower(),
                hashtags=extract_hashtags(text),
                reactions=_int(row.get("reactions")),
                shares=_int(row.get("shares")),
            )
            self.posts[post.post_id] = post
            if _str(row.get("page_name")):
                page_names[post.page_id] = _str(row.get("page_name"))

        self.pages: dict[str, Page] = {}
        if pages is not None:
            for row in self._read(pages).to_dict("records"):
                page = Page(
                    page_id=_str(row["page_id"]),
                    name=_str(row.get("name")),
                    created_at=_ts(row.get("created_at")),
                    admin_countries=split_multi(row.get("admin_countries")),
                    name_changes=_int(row.get("name_changes")),
                    followers=_int(row.get("followers")),
                    category=_str(row.get("category")),
                )
                self.pages[page.page_id] = page
        for post in self.posts.values():
            if post.page_id not in self.pages:
                self.pages[post.page_id] = Page(page_id=post.page_id)
            if not self.pages[post.page_id].name:
                self.pages[post.page_id].name = page_names.get(post.page_id, post.page_id)

        self.domains: dict[str, Domain] = {}
        if domains is not None:
            for row in self._read(domains).to_dict("records"):
                d = Domain(
                    domain=_str(row["domain"]).lower(),
                    tracking_ids=[t.upper() for t in split_multi(row.get("tracking_ids"))],
                    registered_at=_ts(row.get("registered_at")),
                    registrar=_str(row.get("registrar")),
                )
                self.domains[d.domain] = d

        # Lookup indexes.
        self._by_page: dict[str, list[Post]] = defaultdict(list)
        self._by_link: dict[str, list[Post]] = defaultdict(list)
        self._by_permalink: dict[str, Post] = {}
        for post in self.posts.values():
            self._by_page[post.page_id].append(post)
            for link in post.links:
                self._by_link[link].append(post)
            if post.permalink:
                self._by_permalink[canonical_url(post.permalink)] = post
        self._post_list = list(self.posts.values())
        self._text_index = TextIndex([p.text for p in self._post_list])
        self._images = [p for p in self._post_list if p.image_phash]

    @staticmethod
    def _read(source) -> pd.DataFrame:
        if isinstance(source, pd.DataFrame):
            return source
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, dtype=str, keep_default_na=False)

    # --- Connector interface -------------------------------------------------

    def get_post(self, post_id_or_url: str) -> Post | None:
        key = post_id_or_url.strip()
        if key in self.posts:
            return self.posts[key]
        return self._by_permalink.get(canonical_url(key))

    def get_page(self, page_id: str) -> Page | None:
        return self.pages.get(page_id)

    def posts_by_page(self, page_id: str) -> list[Post]:
        return list(self._by_page.get(page_id, []))

    def posts_with_link(self, canonical_link: str) -> list[Post]:
        return list(self._by_link.get(canonical_link, []))

    def posts_with_image(self, phash: str, max_distance: int) -> list[Post]:
        return [p for p in self._images if hamming_hex(p.image_phash, phash) <= max_distance]

    def posts_with_similar_text(self, text: str, min_similarity: float) -> list[Post]:
        return [self._post_list[i] for i, _ in self._text_index.query(text, min_similarity)]

    def get_domain(self, domain: str) -> Domain | None:
        return self.domains.get(domain)

    def domains_with_tracking_id(self, tracking_id: str) -> list[Domain]:
        return [d for d in self.domains.values() if tracking_id.upper() in d.tracking_ids]

    def all_pages(self) -> list[Page]:
        return sorted(self.pages.values(), key=lambda p: p.name or p.page_id)
