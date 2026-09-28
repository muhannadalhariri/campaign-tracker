"""Core data types shared by connectors, the engine and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    post_id: str
    page_id: str
    created_at: datetime
    text: str = ""
    permalink: str = ""
    links: list[str] = field(default_factory=list)  # canonical external URLs
    image_phash: str = ""  # hex perceptual hash of the attached image, if any
    hashtags: list[str] = field(default_factory=list)
    reactions: int = 0
    shares: int = 0


@dataclass
class Page:
    page_id: str
    name: str = ""
    created_at: datetime | None = None
    admin_countries: list[str] = field(default_factory=list)
    name_changes: int = 0
    followers: int = 0
    category: str = ""


@dataclass
class Domain:
    domain: str
    tracking_ids: list[str] = field(default_factory=list)  # UA-/G-/GTM-/ca-pub-
    registered_at: datetime | None = None
    registrar: str = ""


@dataclass
class Evidence:
    """One coordinated event linking two pages."""

    kind: str  # "link" | "text" | "image"
    key: str  # the shared URL / text cluster id / image hash
    post_a: str
    post_b: str
    seconds_apart: float

    def describe(self) -> str:
        labels = {"link": "نفس الرابط", "text": "نص شبه مطابق", "image": "نفس الصورة"}
        return (
            f"{labels.get(self.kind, self.kind)} — {self.post_a} ↔ {self.post_b} "
            f"(بفارق {self.seconds_apart:.0f} ثانية)"
        )


@dataclass
class Seed:
    """Starting point of an investigation."""

    post_ids: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)  # post permalinks or external links

    def is_empty(self) -> bool:
        return not (self.post_ids or self.page_ids or self.urls)
