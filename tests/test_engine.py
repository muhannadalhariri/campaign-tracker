from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from tracker.connectors import CSVConnector
from tracker.coordination import Params, detect
from tracker.expansion import ACCEPTED, Investigation
from tracker.models import Post, Seed
from tracker.network import build_graph, narratives
from tracker.normalize import canonical_url, normalize_text
from tracker.report import json_report
from tracker.similarity import hamming_hex
from tracker.store import Store

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"
T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def post(pid, page, seconds, text="", links=(), phash=""):
    return Post(pid, page, T + timedelta(seconds=seconds), text, links=list(links), image_phash=phash)


# --- normalization -----------------------------------------------------------

def test_arabic_normalization_hides_evasion_edits():
    assert normalize_text("إنـقطاع المياهِ الكاملة!") == normalize_text("انقطاع المياه الكامله")


def test_canonical_url_strips_tracking():
    a = canonical_url("https://www.site.example/news/1/?utm_source=fb&fbclid=abc")
    b = canonical_url("http://m.site.example/news/1")
    assert a == b == "site.example/news/1"


def test_hamming():
    assert hamming_hex("00ff", "00fe") == 1
    assert hamming_hex("00ff", "") > 64


# --- coordination --------------------------------------------------------------

def test_repeated_fast_link_sharing_is_coordination():
    posts = []
    for i in range(3):
        posts += [post(f"a{i}", "A", i * 10000, links=[f"x.example/{i}"]),
                  post(f"b{i}", "B", i * 10000 + 20, links=[f"x.example/{i}"])]
    res = detect(posts, Params(min_events=3))
    assert res.weight("A", "B") == 3


def test_slow_or_single_sharing_is_not_coordination():
    posts = [post("a", "A", 0, links=["x.example/1"]), post("b", "B", 5000, links=["x.example/1"])]
    posts += [post("c", "A", 100, links=["x.example/2"]), post("d", "B", 110, links=["x.example/2"])]
    res = detect(posts, Params(min_events=2))
    assert res.edges == {}


def test_noise_domains_ignored():
    posts = []
    for i in range(4):
        posts += [post(f"a{i}", "A", i * 9000, links=[f"youtube.com/watch?v={i}"]),
                  post(f"b{i}", "B", i * 9000 + 5, links=[f"youtube.com/watch?v={i}"])]
    assert detect(posts, Params(min_events=2)).edges == {}


def test_near_duplicate_text_and_images():
    text = "مصادر خاصة تؤكد انقطاع المياه عن كامل أحياء المدينة لمدة أسبوعين ابتداء من الغد"
    posts = []
    for i in range(3):
        posts += [post(f"a{i}", "A", i * 20000, text=text + f" {i}", phash="ff00ff00ff00ff00"),
                  post(f"b{i}", "B", i * 20000 + 600, text="عاجل: " + text + f" {i}",
                       phash="ff00ff00ff00ff01")]
    res = detect(posts, Params(min_events=3, text_threshold=0.8))
    kinds = {e.kind for e in res.edges[("A", "B")]}
    assert kinds == {"text", "image"}


# --- end-to-end on the synthetic dataset ---------------------------------------

@pytest.fixture(scope="module")
def connector():
    if not (SAMPLE / "posts.csv").exists():
        pytest.skip("run scripts/generate_sample_data.py first")
    return CSVConnector(SAMPLE / "posts.csv", SAMPLE / "pages.csv", SAMPLE / "domains.csv")


def test_seed_post_finds_network_without_organic_pages(connector):
    seed_post = next(p for p in connector.posts.values() if p.page_id == "A01" and p.links)
    inv = Investigation(connector, Seed(post_ids=[seed_post.post_id]))
    inv.start()
    assert inv.accepted == ["A01"]
    found = {c.page_id for c in inv.candidates()}
    assert {f"A{i:02d}" for i in range(2, 11)} <= found
    assert not any(p.startswith("O") for p in found)

    inv.auto_expand(max_hops=3)
    accepted = set(inv.accepted)
    assert {f"B{i:02d}" for i in range(1, 6)} <= accepted
    assert not any(p.startswith("O") for p in accepted)

    g = build_graph(inv)
    domains = {d["label"] for _, d in g.nodes(data=True) if d["kind"] == "domain"}
    assert "hidden-mirror.example" in domains  # reached only via the shared analytics id
    assert not any(d.startswith(("recipes", "football")) for d in domains)
    communities = {g.nodes[p]["community"] for p in accepted}
    assert len(communities) >= 2
    assert narratives(inv)
    assert "evidence" in json_report(inv)


def test_organic_seed_produces_nothing(connector):
    inv = Investigation(connector, Seed(page_ids=["O01", "O02"]))
    inv.start()
    assert inv.candidates() == []


def test_link_seed(connector):
    link = next(l for p in connector.posts.values() if p.page_id.startswith("A") for l in p.links
                if "sahel-truth" in l)
    inv = Investigation(connector, Seed(urls=["https://" + link]))
    inv.start()
    assert any(c.page_id.startswith("A") for c in inv.candidates())


def test_rejected_pages_are_not_expanded_and_state_roundtrips(connector, tmp_path):
    seed_post = next(p for p in connector.posts.values() if p.page_id == "A01" and p.links)
    inv = Investigation(connector, Seed(post_ids=[seed_post.post_id]))
    inv.start()
    inv.reject("A02", "صفحة إخبارية حقيقية")
    inv.accept("A03")
    inv.expand()
    assert "A02" not in inv.expanded and "A03" in inv.expanded

    store = Store(tmp_path / "t.db")
    store.save("demo", inv.to_state())
    restored = Investigation.from_state(connector, store.load("demo"))
    assert restored.decisions == inv.decisions
    assert restored.expanded == inv.expanded
    assert restored.notes["A02"] == "صفحة إخبارية حقيقية"
    assert set(restored.posts) == set(inv.posts)


def test_csv_validation():
    with pytest.raises(ValueError):
        CSVConnector(pd.DataFrame({"post_id": ["1"]}))
