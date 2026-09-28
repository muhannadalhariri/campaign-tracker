"""Seed-based ("snowball") expansion with a human in the loop.

1. Resolve the seed (post / page(s) / link) into anchor pages and posts.
2. Fingerprint the posts of accepted pages: links, text, images.
3. Ask the connector who else published the same fingerprints.
4. Run coordination detection over everything collected.
5. Pages with repeated coordination to accepted pages become *candidates*.
6. The analyst accepts or rejects candidates; only accepted pages are
   expanded in the next hop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .connectors.base import Connector
from .coordination import CoordinationResult, Params, detect
from .models import Post, Seed
from .normalize import canonical_url, domain_of

ACCEPTED = "accepted"
REJECTED = "rejected"


@dataclass
class Candidate:
    page_id: str
    score: int  # number of coordinated events with accepted pages
    linked_to: dict[str, int]  # accepted page -> events
    hop: int


@dataclass
class Investigation:
    connector: Connector
    seed: Seed
    params: Params = field(default_factory=Params)
    max_posts_per_lookup: int = 500

    decisions: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    hops: dict[str, int] = field(default_factory=dict)  # page -> hop it was found at
    expanded: set[str] = field(default_factory=set)
    posts: dict[str, Post] = field(default_factory=dict)
    seed_links: set[str] = field(default_factory=set)
    seed_post_ids: set[str] = field(default_factory=set)
    result: CoordinationResult | None = None
    log: list[str] = field(default_factory=list)

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self.seed.is_empty():
            raise ValueError("Seed is empty")
        c = self.connector
        for pid in self.seed.page_ids:
            if c.get_page(pid) is None and not c.posts_by_page(pid):
                self.log.append(f"الصفحة غير موجودة في مصدر البيانات: {pid}")
                continue
            self._accept(pid, hop=0, note="نقطة انطلاق")
        for ref in list(self.seed.post_ids) + list(self.seed.urls):
            post = c.get_post(ref)
            if post is not None:
                self.seed_post_ids.add(post.post_id)
                self._add_posts([post])
                self._accept(post.page_id, hop=0, note="ناشر منشور الانطلاق")
            elif "://" in ref or "." in ref:
                # Not a known post: treat it as an external link being pushed.
                link = canonical_url(ref)
                self.seed_links.add(link)
                sharers = c.posts_with_link(link)[: self.max_posts_per_lookup]
                self._add_posts(sharers)
                # One shared link is never enough evidence, so look at what the
                # sharers publish to see whether they coordinate repeatedly.
                for page_id in sorted({p.page_id for p in sharers}):
                    self._expand_page(page_id)
                self.log.append(
                    f"رابط انطلاق خارجي: {link} — نشرته {len({p.page_id for p in sharers})} صفحة"
                )
            else:
                self.log.append(f"لم يُعثر على المنشور: {ref}")
        self.expand()

    def expand(self, only: set[str] | None = None) -> None:
        """Expand accepted pages that have not been expanded yet (optionally a subset)."""
        todo = [
            p for p, s in self.decisions.items()
            if s == ACCEPTED and p not in self.expanded and (only is None or p in only)
        ]
        for page_id in todo:
            self._expand_page(page_id)
            self.expanded.add(page_id)
        self.result = detect(list(self.posts.values()), self.params)
        hop = max((self.hops.get(p, 0) for p in todo), default=0) + 1
        for cand in self.candidates():
            self.hops.setdefault(cand.page_id, hop)
        self.log.append(
            f"توسيع {len(todo)} صفحة — {len(self.posts)} منشور، "
            f"{len(self.result.edges)} ارتباط منسّق"
        )

    def auto_expand(self, max_hops: int, min_score: int | None = None) -> None:
        """Accept every candidate above `min_score` for up to `max_hops` rounds.

        Meant for demos and triage only: real findings need human review.
        """
        for _ in range(max_hops):
            new = [c for c in self.candidates() if c.score >= (min_score or self.params.min_events)]
            if not new:
                break
            for cand in new:
                self._accept(cand.page_id, hop=cand.hop, note="قبول آلي")
            self.expand()

    # --- decisions -----------------------------------------------------------

    def accept(self, page_id: str, note: str = "") -> None:
        self._accept(page_id, self.hops.get(page_id, 0), note)

    def reject(self, page_id: str, note: str = "") -> None:
        self.decisions[page_id] = REJECTED
        if note:
            self.notes[page_id] = note

    def undecide(self, page_id: str) -> None:
        self.decisions.pop(page_id, None)

    def _accept(self, page_id: str, hop: int, note: str = "") -> None:
        self.decisions[page_id] = ACCEPTED
        self.hops.setdefault(page_id, hop)
        if note:
            self.notes.setdefault(page_id, note)

    # --- views ---------------------------------------------------------------

    @property
    def accepted(self) -> list[str]:
        return [p for p, s in self.decisions.items() if s == ACCEPTED]

    @property
    def rejected(self) -> list[str]:
        return [p for p, s in self.decisions.items() if s == REJECTED]

    def candidates(self) -> list[Candidate]:
        if self.result is None:
            return []
        accepted = set(self.accepted)
        scores: dict[str, dict[str, int]] = {}
        for (a, b), ev in self.result.edges.items():
            for x, y in ((a, b), (b, a)):
                if x in self.decisions:
                    continue
                # With no accepted pages yet (link-only seed) any edge counts.
                if y in accepted or not accepted:
                    scores.setdefault(x, {})[y] = len(ev)
        out = [
            Candidate(p, sum(links.values()), links, self.hops.get(p, 1))
            for p, links in scores.items()
        ]
        return sorted(out, key=lambda c: -c.score)

    def page_posts(self, page_id: str) -> list[Post]:
        return sorted((p for p in self.posts.values() if p.page_id == page_id),
                      key=lambda p: p.created_at)

    # --- persistence ---------------------------------------------------------

    def to_state(self) -> dict:
        return {
            "seed": asdict(self.seed),
            "params": {**asdict(self.params), "noise_domains": sorted(self.params.noise_domains)},
            "decisions": self.decisions,
            "notes": self.notes,
            "hops": self.hops,
            "expanded": sorted(self.expanded),
        }

    @classmethod
    def from_state(cls, connector: Connector, state: dict) -> "Investigation":
        params = Params(**{**state["params"], "noise_domains": set(state["params"]["noise_domains"])})
        inv = cls(connector=connector, seed=Seed(**state["seed"]), params=params)
        inv.start()
        # Replay the saved decisions, expanding exactly the pages that were expanded.
        inv.decisions.update(state["decisions"])
        inv.notes.update(state["notes"])
        inv.hops.update(state["hops"])
        inv.expand(only=set(state["expanded"]))
        return inv

    # --- internals -----------------------------------------------------------

    def _add_posts(self, posts: list[Post]) -> None:
        for p in posts:
            self.posts.setdefault(p.post_id, p)

    def _expand_page(self, page_id: str) -> None:
        c, cap = self.connector, self.max_posts_per_lookup
        own = c.posts_by_page(page_id)
        self._add_posts(own)
        seen_links, seen_images = set(), set()
        for post in own:
            for link in post.links:
                if link in seen_links or domain_of("https://" + link) in self.params.noise_domains:
                    continue
                seen_links.add(link)
                self._add_posts(c.posts_with_link(link)[:cap])
            if post.image_phash and post.image_phash not in seen_images:
                seen_images.add(post.image_phash)
                self._add_posts(c.posts_with_image(post.image_phash, self.params.image_max_distance)[:cap])
            self._add_posts(c.posts_with_similar_text(post.text, self.params.text_threshold)[:cap])
