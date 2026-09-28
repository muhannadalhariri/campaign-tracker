"""Evidence export: every claim in the network traceable to concrete posts."""

from __future__ import annotations

import json

import pandas as pd

from .expansion import Investigation
from .network import narratives


def evidence_table(inv: Investigation, accepted_only: bool = True) -> pd.DataFrame:
    rows = []
    if inv.result is None:
        return pd.DataFrame()
    keep = set(inv.accepted)
    for (a, b), evidence in inv.result.edges.items():
        if accepted_only and not (a in keep and b in keep):
            continue
        for ev in evidence:
            pa, pb = inv.posts.get(ev.post_a), inv.posts.get(ev.post_b)
            rows.append({
                "page_a": a,
                "page_b": b,
                "type": ev.kind,
                "content": ev.key,
                "post_a": ev.post_a,
                "post_a_link": pa.permalink if pa else "",
                "post_a_time": pa.created_at.isoformat() if pa else "",
                "post_b": ev.post_b,
                "post_b_link": pb.permalink if pb else "",
                "post_b_time": pb.created_at.isoformat() if pb else "",
                "seconds_apart": round(ev.seconds_apart),
            })
    return pd.DataFrame(rows)


def pages_table(inv: Investigation) -> pd.DataFrame:
    rows = []
    for page_id, status in inv.decisions.items():
        page = inv.connector.get_page(page_id)
        rows.append({
            "page_id": page_id,
            "name": page.name if page else "",
            "status": status,
            "hop": inv.hops.get(page_id, 0),
            "note": inv.notes.get(page_id, ""),
            "created_at": page.created_at.date().isoformat() if page and page.created_at else "",
            "admin_countries": "|".join(page.admin_countries) if page else "",
            "name_changes": page.name_changes if page else 0,
            "followers": page.followers if page else 0,
        })
    return pd.DataFrame(rows)


def json_report(inv: Investigation) -> str:
    return json.dumps(
        {
            "investigation": inv.to_state(),
            "pages": pages_table(inv).to_dict("records"),
            "narratives": [
                {
                    "type": n.cluster.kind,
                    "content": n.cluster.label,
                    "origin_page": n.origin_page,
                    "origin_post": n.cluster.origin.post_id,
                    "origin_time": n.cluster.origin.created_at.isoformat(),
                    "pages": n.pages_in_network,
                    "spread_minutes": round(n.spread_minutes, 1),
                }
                for n in narratives(inv)
            ],
            "evidence": evidence_table(inv).to_dict("records"),
            "disclaimer": (
                "Coordination is not proof of disinformation. Every link must be "
                "verified by a human analyst before any public attribution."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
