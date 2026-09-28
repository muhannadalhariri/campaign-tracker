"""Turn an investigation into an analyzable network.

Page nodes are linked by coordination edges; domain nodes show which websites
the network pushes, and domains are linked to each other when they share the
same analytics / ad tracking id (a strong sign of common ownership).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import networkx as nx

from .coordination import ContentCluster
from .expansion import ACCEPTED, Investigation
from .normalize import domain_of

CANDIDATE = "candidate"
BATCH_CREATION_DAYS = 14


@dataclass
class Narrative:
    cluster: ContentCluster
    origin_page: str
    pages_in_network: list[str]
    spread_minutes: float  # origin -> last post in network


def build_graph(inv: Investigation, include_candidates: bool = True,
                include_domains: bool = True) -> nx.Graph:
    g = nx.Graph()
    c = inv.connector
    status = {p: ACCEPTED for p in inv.accepted}
    if include_candidates:
        for cand in inv.candidates():
            status[cand.page_id] = CANDIDATE

    for page_id, st in status.items():
        page = c.get_page(page_id)
        g.add_node(
            page_id,
            kind="page",
            label=(page.name if page and page.name else page_id),
            status=st,
            hop=inv.hops.get(page_id, 0),
            followers=page.followers if page else 0,
            created_at=page.created_at.isoformat() if page and page.created_at else "",
            admin_countries=", ".join(page.admin_countries) if page else "",
            name_changes=page.name_changes if page else 0,
            note=inv.notes.get(page_id, ""),
        )

    if inv.result:
        for (a, b), evidence in inv.result.edges.items():
            if a in g and b in g:
                kinds = Counter(e.kind for e in evidence)
                g.add_edge(a, b, kind="coordination", weight=len(evidence),
                           kinds=dict(kinds), evidence=evidence)

    _annotate_pages(g, inv)
    if include_domains:
        _add_domains(g, inv)
    return g


def _annotate_pages(g: nx.Graph, inv: Investigation) -> None:
    pages = [n for n, d in g.nodes(data=True) if d["kind"] == "page"]
    sub = g.subgraph(pages)
    if sub.number_of_edges():
        communities = sorted(
            nx.community.louvain_communities(sub, weight="weight", seed=42),
            key=lambda c: (-len(c), min(c)),
        )  # biggest community first, so colors stay stable
        centrality = nx.degree_centrality(sub)
        strength = dict(sub.degree(weight="weight"))
    else:
        communities, centrality, strength = [], {}, {}
    community_of = {n: i for i, comm in enumerate(communities) for n in comm}

    origins = Counter(n.origin_page for n in narratives(inv))
    created = {
        n: inv.connector.get_page(n).created_at
        for n in pages
        if inv.connector.get_page(n) and inv.connector.get_page(n).created_at
    }
    for n in pages:
        d = g.nodes[n]
        d["community"] = community_of.get(n, -1)
        d["centrality"] = round(centrality.get(n, 0.0), 3)
        d["strength"] = strength.get(n, 0)
        d["origin_count"] = origins.get(n, 0)
        d["posts"] = len(inv.page_posts(n))
        if n in created:
            close = [m for m in created if m != n
                     and abs((created[m] - created[n]).days) <= BATCH_CREATION_DAYS]
            d["created_with"] = len(close)
        else:
            d["created_with"] = 0


def _add_domains(g: nx.Graph, inv: Investigation) -> None:
    c = inv.connector
    accepted = set(inv.accepted)
    shares: dict[str, Counter] = defaultdict(Counter)
    for post in inv.posts.values():
        if post.page_id not in accepted:
            continue
        for link in post.links:
            dom = domain_of("https://" + link)
            if dom and dom not in inv.params.noise_domains:
                shares[dom][post.page_id] += 1

    # Keep only domains whose links were part of coordinated events inside the
    # network: pages also share ordinary sites, which says nothing.
    coordinated_links = {
        ev.key.split(":", 1)[1].rsplit("#", 1)[0]
        for (a, b), evidence in (inv.result.edges.items() if inv.result else [])
        if a in accepted and b in accepted
        for ev in evidence if ev.kind == "link"
    }
    domains = {domain_of("https://" + link) for link in coordinated_links} & set(shares)
    # Follow shared tracking ids one step out, even to sites the pages never linked.
    extra = set()
    for dom in list(domains):
        info = c.get_domain(dom)
        for tid in (info.tracking_ids if info else []):
            extra.update(o.domain for o in c.domains_with_tracking_id(tid))
    domains |= extra

    for dom in domains:
        info = c.get_domain(dom)
        g.add_node(
            f"domain:{dom}",
            kind="domain",
            label=dom,
            status="domain",
            tracking_ids=", ".join(info.tracking_ids) if info else "",
            registered_at=info.registered_at.isoformat() if info and info.registered_at else "",
            registrar=info.registrar if info else "",
            community=-1,
        )
        for page_id, count in shares.get(dom, {}).items():
            if page_id in g:
                g.add_edge(page_id, f"domain:{dom}", kind="promotes", weight=count)

    dom_list = sorted(domains)
    for i, a in enumerate(dom_list):
        ia = c.get_domain(a)
        for b in dom_list[i + 1:]:
            ib = c.get_domain(b)
            if ia and ib:
                shared = sorted(set(ia.tracking_ids) & set(ib.tracking_ids))
                if shared:
                    g.add_edge(f"domain:{a}", f"domain:{b}", kind="same_owner",
                               weight=len(shared), tracking_ids=shared)


def narratives(inv: Investigation, min_pages: int = 2) -> list[Narrative]:
    """Content clusters carried by accepted pages, with their origin ("patient zero")."""
    if inv.result is None:
        return []
    accepted = set(inv.accepted)
    # Only content that produced coordination evidence between network pages.
    coordinated = {
        ev.key
        for (a, b), evidence in inv.result.edges.items()
        if a in accepted and b in accepted
        for ev in evidence
    }
    out = []
    for cl in inv.result.clusters:
        if cl.cluster_id not in coordinated:
            continue
        in_net = [p for p in cl.posts if p.page_id in accepted]
        pages = sorted({p.page_id for p in in_net})
        if len(pages) < min_pages:
            continue
        spread = (in_net[-1].created_at - cl.origin.created_at).total_seconds() / 60
        out.append(Narrative(cl, cl.origin.page_id, pages, spread))
    return sorted(out, key=lambda n: (-len(n.pages_in_network), n.cluster.origin.created_at))
