"""Coordination detection.

Two pages are linked when they repeatedly publish the *same content* within a
*short time window*: the same external link (the CooRnet method), a
near-duplicate text, or the same image. A single co-share is treated as
coincidence; only repeated events (``min_events``) produce an edge.

Every edge carries its evidence so an analyst can verify it by hand.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from .models import Evidence, Post
from .normalize import domain_of
from .similarity import hamming_hex, similar_pairs

# Sites that everyone links to; sharing them says nothing about coordination.
DEFAULT_NOISE_DOMAINS = {
    "facebook.com", "fb.watch", "youtube.com", "youtu.be", "twitter.com", "x.com",
    "instagram.com", "t.me", "tiktok.com", "google.com", "wikipedia.org",
    "bbc.com", "bbc.co.uk", "aljazeera.net", "aljazeera.com", "reuters.com",
    "apnews.com", "cnn.com", "skynewsarabia.com", "alarabiya.net", "france24.com",
}


@dataclass
class Params:
    link_window_s: int = 60
    content_window_s: int = 3600
    text_threshold: float = 0.85
    image_max_distance: int = 6
    min_events: int = 3
    noise_domains: set[str] = field(default_factory=lambda: set(DEFAULT_NOISE_DOMAINS))


@dataclass
class ContentCluster:
    """A piece of content (link, text or image) and every post that carried it."""

    cluster_id: str
    kind: str  # "link" | "text" | "image"
    label: str
    posts: list[Post]

    @property
    def origin(self) -> Post:
        return self.posts[0]

    @property
    def page_ids(self) -> list[str]:
        return sorted({p.page_id for p in self.posts})


@dataclass
class CoordinationResult:
    # (page_a, page_b) with page_a < page_b -> evidence, one entry per shared cluster
    edges: dict[tuple[str, str], list[Evidence]]
    clusters: list[ContentCluster]

    def weight(self, a: str, b: str) -> int:
        return len(self.edges.get(tuple(sorted((a, b))), []))

    def neighbors(self, page_id: str) -> dict[str, list[Evidence]]:
        out = {}
        for (a, b), ev in self.edges.items():
            if a == page_id:
                out[b] = ev
            elif b == page_id:
                out[a] = ev
        return out


def _components(n: int, pairs) -> list[list[int]]:
    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from((i, j) for i, j, *_ in pairs)
    return [sorted(c) for c in nx.connected_components(g) if len(c) > 1]


def _pair_events(cluster: ContentCluster, window_s: int) -> dict[tuple[str, str], Evidence]:
    """Closest-in-time pair of posts for every page pair inside one cluster."""
    posts = cluster.posts  # sorted by time
    best: dict[tuple[str, str], Evidence] = {}
    start = 0
    for j, pj in enumerate(posts):
        while (pj.created_at - posts[start].created_at).total_seconds() > window_s:
            start += 1
        for i in range(start, j):
            pi = posts[i]
            if pi.page_id == pj.page_id:
                continue
            gap = (pj.created_at - pi.created_at).total_seconds()
            key = tuple(sorted((pi.page_id, pj.page_id)))
            if key not in best or gap < best[key].seconds_apart:
                best[key] = Evidence(cluster.kind, cluster.cluster_id, pi.post_id, pj.post_id, gap)
    return best


def _waves(group: list[Post], gap_s: int) -> list[list[Post]]:
    """Split time-sorted posts into waves separated by more than `gap_s` of silence.

    The same rumor re-pushed on another day is a new wave, so each wave has
    a meaningful origin and spread time.
    """
    waves = [[group[0]]]
    for prev, cur in zip(group, group[1:]):
        if (cur.created_at - prev.created_at).total_seconds() > gap_s:
            waves.append([])
        waves[-1].append(cur)
    return [w for w in waves if len({p.page_id for p in w}) > 1]


def build_clusters(posts: list[Post], params: Params) -> list[tuple[ContentCluster, int]]:
    """Group posts by shared content. Returns (cluster, time window) pairs."""
    out: list[tuple[ContentCluster, int]] = []
    gap = params.content_window_s

    def emit(kind: str, key: str, label_of, group: list[Post], window: int) -> None:
        group = sorted(group, key=lambda p: p.created_at)
        for k, wave in enumerate(_waves(group, max(gap, window))):
            cid = f"{kind}:{key}#{k}"
            out.append((ContentCluster(cid, kind, label_of(wave), wave), window))

    by_link: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        for link in p.links:
            if domain_of("https://" + link) not in params.noise_domains:
                by_link[link].append(p)
    for link, group in by_link.items():
        emit("link", link, lambda w, link=link: link, group, params.link_window_s)

    pairs = similar_pairs([p.text for p in posts], params.text_threshold)
    for comp in _components(len(posts), pairs):
        group = [posts[i] for i in comp]
        first = min(group, key=lambda p: p.created_at)
        emit("text", first.post_id, lambda w: w[0].text[:80], group, params.content_window_s)

    imaged = [p for p in posts if p.image_phash]
    img_pairs = [
        (i, j)
        for i in range(len(imaged))
        for j in range(i + 1, len(imaged))
        if hamming_hex(imaged[i].image_phash, imaged[j].image_phash) <= params.image_max_distance
    ]
    for comp in _components(len(imaged), img_pairs):
        group = [imaged[i] for i in comp]
        first = min(group, key=lambda p: p.created_at)
        emit("image", first.image_phash, lambda w: w[0].image_phash, group, params.content_window_s)
    return out


def detect(posts: list[Post], params: Params) -> CoordinationResult:
    unique = list({p.post_id: p for p in posts}.values())
    edges: dict[tuple[str, str], list[Evidence]] = defaultdict(list)
    clusters = []
    for cluster, window in build_clusters(unique, params):
        clusters.append(cluster)
        for key, ev in _pair_events(cluster, window).items():
            edges[key].append(ev)
    kept = {k: v for k, v in edges.items() if len(v) >= params.min_events}
    clusters.sort(key=lambda c: (-len(c.page_ids), c.origin.created_at))
    return CoordinationResult(edges=kept, clusters=clusters)
