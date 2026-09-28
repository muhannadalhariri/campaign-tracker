"""Streamlit interface.  Run:  streamlit run app.py"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from tracker.connectors import CSVConnector
from tracker.coordination import DEFAULT_NOISE_DOMAINS, Params
from tracker.expansion import ACCEPTED, REJECTED, Investigation
from tracker.models import Seed
from tracker.network import CANDIDATE, build_graph, narratives
from tracker.report import evidence_table, json_report, pages_table
from tracker.store import Store

SAMPLE = Path(__file__).parent / "data" / "sample"
# Categorical slots in fixed order (validated palette); communities beyond 8 fold to gray.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER = "#8c8b86"
CANDIDATE_COLOR = "#c9c8c2"
DOMAIN_COLOR = "#52514e"
KIND_AR = {"link": "رابط", "text": "نص", "image": "صورة"}

st.set_page_config(page_title="متتبّع الحملات المنسّقة", page_icon="🕸️", layout="wide")
st.markdown(
    """
    <style>
      .stApp, .stMarkdown, .stTextInput, .stTextArea, .stSelectbox, .stMultiSelect,
      [data-testid="stSidebar"], [data-testid="stExpander"] { direction: rtl; text-align: right; }
      [data-testid="stDataFrame"], code, pre { direction: ltr; text-align: left; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- data source -----------------------------------------------------------------

@st.cache_resource(show_spinner="تحميل البيانات التجريبية…")
def sample_connector() -> CSVConnector:
    return CSVConnector(SAMPLE / "posts.csv", SAMPLE / "pages.csv", SAMPLE / "domains.csv")


@st.cache_resource(show_spinner="قراءة الملفات…")
def uploaded_connector(posts_bytes: bytes, pages_bytes: bytes | None, domains_bytes: bytes | None):
    import io
    return CSVConnector(
        io.BytesIO(posts_bytes),
        io.BytesIO(pages_bytes) if pages_bytes else None,
        io.BytesIO(domains_bytes) if domains_bytes else None,
    )


@st.cache_resource
def store() -> Store:
    return Store(Path(__file__).parent / "tracker.db")


def page_label(connector, page_id: str) -> str:
    page = connector.get_page(page_id)
    return f"{page.name} [{page_id}]" if page and page.name else page_id


with st.sidebar:
    st.header("مصدر البيانات")
    source = st.radio("المصدر", ["بيانات تجريبية (وهمية)", "رفع ملفات CSV"], label_visibility="collapsed")
    connector = None
    if source.startswith("بيانات"):
        if (SAMPLE / "posts.csv").exists():
            connector = sample_connector()
        else:
            st.error("شغّل أولاً: python scripts/generate_sample_data.py")
    else:
        posts_file = st.file_uploader("posts.csv (إلزامي)", type="csv")
        pages_file = st.file_uploader("pages.csv (اختياري)", type="csv")
        domains_file = st.file_uploader("domains.csv (اختياري)", type="csv")
        if posts_file:
            try:
                connector = uploaded_connector(
                    posts_file.getvalue(),
                    pages_file.getvalue() if pages_file else None,
                    domains_file.getvalue() if domains_file else None,
                )
            except ValueError as e:
                st.error(str(e))
    if connector is not None:
        st.caption(f"{len(connector.posts)} منشور · {len(connector.pages)} صفحة · {len(connector.domains)} نطاق")

    st.header("معايير التنسيق")
    link_window = st.slider("نافذة مشاركة الرابط (ثوانٍ)", 10, 600, 60, 10)
    content_window = st.slider("نافذة النص/الصورة (دقائق)", 5, 360, 60, 5)
    text_threshold = st.slider("حد تشابه النص", 0.5, 1.0, 0.85, 0.01)
    image_distance = st.slider("أقصى فرق لبصمة الصورة (bits)", 0, 16, 6)
    min_events = st.slider("أقل عدد أحداث منسّقة للارتباط", 1, 10, 3)
    extra_noise = st.text_area("نطاقات إضافية تُتجاهل (سطر لكل نطاق)", "")
    params = Params(
        link_window_s=link_window,
        content_window_s=content_window * 60,
        text_threshold=text_threshold,
        image_max_distance=image_distance,
        min_events=min_events,
        noise_domains=DEFAULT_NOISE_DOMAINS | {d.strip().lower() for d in extra_noise.split() if d.strip()},
    )

    st.header("التحقيقات المحفوظة")
    saved = store().list()
    if saved and connector is not None:
        choice = st.selectbox("فتح تحقيق", [n for n, _ in saved])
        c1, c2 = st.columns(2)
        if c1.button("فتح"):
            st.session_state.inv = Investigation.from_state(connector, store().load(choice))
            st.session_state.inv_name = choice
            st.rerun()
        if c2.button("حذف"):
            store().delete(choice)
            st.rerun()
    elif not saved:
        st.caption("لا توجد تحقيقات محفوظة بعد.")

st.title("🕸️ متتبّع الحملات المنسّقة")
st.info(
    "**التنسيق ليس دليلاً على التضليل بحد ذاته.** هذه الأداة تكشف صفحات تنشر المحتوى نفسه "
    "بشكل متزامن ومتكرر، ولكل ارتباط أدلة قابلة للتحقق. لا تنسب أي صفحة لحملة علناً قبل "
    "مراجعة بشرية للأدلة، وركّز على الصفحات والسلوك لا على الأفراد.",
    icon="⚖️",
)

if connector is None:
    st.stop()

# --- seed ------------------------------------------------------------------------

inv: Investigation | None = st.session_state.get("inv")

with st.expander("نقطة الانطلاق", expanded=inv is None):
    refs = st.text_area(
        "روابط أو معرّفات منشورات، أو روابط خارجية مروَّجة (سطر لكل عنصر)",
        placeholder="https://www.facebook.com/…/posts/…\np00004\nhttps://site.example/article",
    )
    all_pages = connector.all_pages()
    seed_pages = st.multiselect(
        "و/أو صفحات", [p.page_id for p in all_pages], format_func=lambda p: page_label(connector, p)
    )
    if source.startswith("بيانات"):
        demo = next((p for p in connector.posts.values() if p.page_id == "A01" and p.links), None)
        if demo:
            st.caption(f"للتجربة: جرّب المنشور `{demo.post_id}` أو الصفحتين O01 و O02 (صفحات عادية).")
    if st.button("ابدأ التحقيق", type="primary"):
        seed = Seed(
            post_ids=[r.strip() for r in refs.splitlines() if r.strip() and "://" not in r and "." not in r],
            urls=[r.strip() for r in refs.splitlines() if r.strip() and ("://" in r or "." in r)],
            page_ids=seed_pages,
        )
        if seed.is_empty():
            st.warning("أدخل منشوراً أو رابطاً أو صفحة واحدة على الأقل.")
        else:
            with st.spinner("جمع البصمات والبحث عن المرتبطين…"):
                new = Investigation(connector, seed, params)
                new.start()
            st.session_state.inv = new
            st.session_state.inv_name = ""
            st.rerun()

if inv is None:
    st.stop()

# Parameters changed in the sidebar apply to the open investigation.
if inv.params != params:
    inv.params = params
    inv.expand()

for line in inv.log[-3:]:
    st.caption("• " + line)

candidates = inv.candidates()
graph = build_graph(inv)
page_nodes = [n for n, d in graph.nodes(data=True) if d["kind"] == "page" and d["status"] == ACCEPTED]
communities = {graph.nodes[n]["community"] for n in page_nodes if graph.nodes[n]["community"] >= 0}

m = st.columns(5)
m[0].metric("صفحات مقبولة", len(inv.accepted))
m[1].metric("مرشّحة للمراجعة", len(candidates))
m[2].metric("مستبعدة", len(inv.rejected))
m[3].metric("منشورات مجمّعة", len(inv.posts))
m[4].metric("تجمعات", len(communities))


def community_color(c: int) -> str:
    # Communities are numbered by size order, so the biggest keep the first slots.
    return SERIES[c] if 0 <= c < len(SERIES) else OTHER


tab_review, tab_net, tab_narr, tab_export = st.tabs(
    ["🔎 مراجعة المرشّحين", "🕸️ الشبكة", "🧵 السرديات والخط الزمني", "📦 الأدلة والتصدير"]
)

# --- review ----------------------------------------------------------------------

with tab_review:
    b1, b2, b3 = st.columns([1, 1, 2])
    pending = [p for p in inv.accepted if p not in inv.expanded]
    if b1.button(f"توسيع من المقبولة ({len(pending)})", disabled=not pending, type="primary"):
        with st.spinner("توسيع…"):
            inv.expand()
        st.rerun()
    if b2.button("قبول آلي لقفزتين (للتجربة فقط)"):
        with st.spinner("توسيع آلي…"):
            inv.auto_expand(max_hops=2)
        st.rerun()
    b3.caption("اقبل أو استبعد المرشّحين، ثم اضغط «توسيع» لتنطلق القفزة التالية من المقبولين فقط.")

    if not candidates:
        st.success("لا يوجد مرشّحون حالياً فوق حد الارتباط.")
    for cand in candidates[:40]:
        page = connector.get_page(cand.page_id)
        head = f"{page_label(connector, cand.page_id)} — {cand.score} حدث منسّق · القفزة {cand.hop}"
        with st.expander(head):
            info = st.columns(4)
            info[0].write(f"**أُنشئت:** {page.created_at.date() if page and page.created_at else '—'}")
            info[1].write(f"**دول المشرفين:** {', '.join(page.admin_countries) if page and page.admin_countries else '—'}")
            info[2].write(f"**تغييرات الاسم:** {page.name_changes if page else '—'}")
            info[3].write(f"**المتابعون:** {f'{page.followers:,}' if page else '—'}")
            st.write("**مرتبطة بـ:** " + "، ".join(
                f"{page_label(connector, p)} ({n})" for p, n in sorted(cand.linked_to.items(), key=lambda x: -x[1])
            ))
            rows = []
            for other in cand.linked_to:
                for ev in inv.result.edges.get(tuple(sorted((cand.page_id, other))), [])[:15]:
                    pa, pb = inv.posts[ev.post_a], inv.posts[ev.post_b]
                    rows.append({
                        "النوع": KIND_AR[ev.kind],
                        "الفارق (ث)": round(ev.seconds_apart),
                        "الأول": f"{pa.page_id} · {pa.created_at:%Y-%m-%d %H:%M:%S}",
                        "الثاني": f"{pb.page_id} · {pb.created_at:%Y-%m-%d %H:%M:%S}",
                        "المحتوى": (pa.links[0] if ev.kind == "link" and pa.links else pa.text[:90]),
                    })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            note = st.text_input("ملاحظة", key=f"note_{cand.page_id}")
            a, r = st.columns(2)
            if a.button("✅ قبول", key=f"acc_{cand.page_id}"):
                inv.accept(cand.page_id, note)
                st.rerun()
            if r.button("❌ استبعاد", key=f"rej_{cand.page_id}"):
                inv.reject(cand.page_id, note)
                st.rerun()

    decided = pages_table(inv)
    if not decided.empty:
        st.subheader("القرارات")
        st.dataframe(decided, hide_index=True, width="stretch")
        undo = st.selectbox("التراجع عن قرار", [""] + list(decided["page_id"]),
                            format_func=lambda p: page_label(connector, p) if p else "—")
        if undo and st.button("تراجع"):
            inv.undecide(undo)
            inv.expanded.discard(undo)
            inv.expand()
            st.rerun()

# --- network ---------------------------------------------------------------------

with tab_net:
    o1, o2 = st.columns(2)
    show_candidates = o1.toggle("إظهار المرشّحين", value=True)
    show_domains = o2.toggle("إظهار المواقع الخارجية", value=True)
    g = build_graph(inv, include_candidates=show_candidates, include_domains=show_domains)
    if g.number_of_nodes() == 0:
        st.info("لا توجد عُقد بعد.")
    else:
        net = Network(height="650px", width="100%", bgcolor="#fcfcfb", font_color="#0b0b0b", cdn_resources="in_line")
        net.set_options("""{
          "physics": {"barnesHut": {"gravitationalConstant": -9000, "springLength": 160,
                                     "avoidOverlap": 0.3},
                      "stabilization": {"iterations": 400, "fit": true}},
          "edges": {"smooth": false, "scaling": {"min": 1, "max": 6}},
          "nodes": {"font": {"size": 13, "face": "sans-serif"}},
          "interaction": {"hover": true, "tooltipDelay": 120}
        }""")
        max_strength = max((d.get("strength", 0) for _, d in g.nodes(data=True)), default=1) or 1
        for n, d in g.nodes(data=True):
            if d["kind"] == "domain":
                title = f"موقع: {d['label']}\nمعرّفات التتبع: {d['tracking_ids'] or '—'}\nتاريخ التسجيل: {d['registered_at'] or '—'}"
                net.add_node(n, label=d["label"], title=title, shape="square", size=14, color=DOMAIN_COLOR)
                continue
            color = CANDIDATE_COLOR if d["status"] == CANDIDATE else community_color(d["community"])
            title = (
                f"{d['label']} [{n}]\nالحالة: {'مرشّحة' if d['status'] == CANDIDATE else 'مقبولة'}"
                f" · القفزة {d['hop']}\nالتجمع: {d['community'] + 1 if d['community'] >= 0 else '—'}"
                f"\nقوة الارتباط: {d['strength']} · بدأ {d['origin_count']} سردية"
                f"\nأُنشئت: {d['created_at'][:10] or '—'} (مع {d['created_with']} صفحة في نفس الأسبوعين)"
                f"\nدول المشرفين: {d['admin_countries'] or '—'} · تغييرات الاسم: {d['name_changes']}"
            )
            net.add_node(
                n, label=d["label"], title=title, color=color,
                size=12 + 28 * d.get("strength", 0) / max_strength,
                borderWidth=3 if d["origin_count"] else 1,
                shapeProperties={"borderDashes": [4, 4]} if d["status"] == CANDIDATE else {},
            )
        for a, b, d in g.edges(data=True):
            if d["kind"] == "coordination":
                kinds = "، ".join(f"{KIND_AR[k]}: {v}" for k, v in d["kinds"].items())
                net.add_edge(a, b, value=d["weight"], title=f"{d['weight']} حدث منسّق ({kinds})", color="#8c8b86")
            elif d["kind"] == "same_owner":
                net.add_edge(a, b, value=3, dashes=True, color="#e34948",
                             title="نفس معرّف التتبع: " + ", ".join(d["tracking_ids"]))
            else:
                net.add_edge(a, b, value=1, color="#d8d7d1", title=f"روّجت الموقع {d['weight']} مرة")
        html = net.generate_html()
        # The graph is laid out while its tab may still be hidden (zero size), so
        # re-fit the view whenever it becomes visible or is resized.
        html = html.replace(
            "network = new vis.Network(container, data, options);",
            "network = new vis.Network(container, data, options);"
            "network.once('stabilizationIterationsDone', () => network.fit());"
            "new ResizeObserver(() => network.fit()).observe(container);",
        )
        components.html(html, height=670, scrolling=False)
        st.caption(
            "الألوان = التجمعات (Louvain) · رمادي منقّط = مرشّح لم يُراجع · مربع = موقع خارجي · "
            "خط أحمر متقطع = مواقع تتشارك معرّف تحليلات/إعلانات (مؤشر ملكية مشتركة) · "
            "الحجم = قوة الارتباط · الإطار العريض = صفحة كانت أول من نشر سردية."
        )

        rows = [
            {"الصفحة": page_label(connector, n), "التجمع": d["community"] + 1 if d["community"] >= 0 else None,
             "الحالة": "مرشّحة" if d["status"] == CANDIDATE else "مقبولة", "قوة الارتباط": d["strength"],
             "المركزية": d["centrality"], "سرديات بدأتها": d["origin_count"], "القفزة": d["hop"]}
            for n, d in g.nodes(data=True) if d["kind"] == "page"
        ]
        st.dataframe(pd.DataFrame(rows).sort_values("قوة الارتباط", ascending=False), hide_index=True, width="stretch")

# --- narratives ------------------------------------------------------------------

with tab_narr:
    narr = narratives(inv)
    if not narr:
        st.info("اقبل صفحتين على الأقل لرؤية السرديات المنسّقة بينها.")
    else:
        origin_counts = pd.Series([n.origin_page for n in narr]).value_counts()
        st.subheader("من يبدأ السرديات؟")
        st.caption("عدد موجات المحتوى المنسّق التي نشرتها كل صفحة أولاً — الصفحات في الأعلى هي غالباً «المصدر».")
        top = origin_counts.head(10).rename_axis("page").reset_index(name="count")
        top["page"] = top["page"].map(lambda p: page_label(connector, p))
        fig = px.bar(top, x="count", y="page", orientation="h", labels={"count": "سرديات بدأتها", "page": ""})
        fig.update_traces(marker_color=SERIES[0], hovertemplate="%{y}: %{x}<extra></extra>")
        fig.update_layout(height=40 * len(top) + 80, yaxis=dict(autorange="reversed"),
                          margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#fcfcfb")
        st.plotly_chart(fig, width="stretch")

        st.subheader("تتبّع سردية")
        idx = st.selectbox(
            "السردية", range(len(narr)),
            format_func=lambda i: (
                f"[{KIND_AR[narr[i].cluster.kind]}] {narr[i].cluster.label[:70]} — "
                f"{len(narr[i].pages_in_network)} صفحة · {narr[i].cluster.origin.created_at:%Y-%m-%d %H:%M}"
            ),
        )
        n = narr[idx]
        origin = n.cluster.origin
        st.write(
            f"**المصدر الأول:** {page_label(connector, origin.page_id)} في "
            f"{origin.created_at:%Y-%m-%d %H:%M:%S} · انتشرت إلى {len(n.pages_in_network)} صفحة خلال "
            f"{n.spread_minutes:.1f} دقيقة"
        )
        if origin.permalink:
            st.write(f"[فتح المنشور الأول]({origin.permalink})")
        comm = {p: graph.nodes[p]["community"] if p in graph else -1 for p in n.pages_in_network}
        df = pd.DataFrame([
            {"الوقت": p.created_at, "الصفحة": page_label(connector, p.page_id),
             "التجمع": str(comm.get(p.page_id, -1) + 1) if comm.get(p.page_id, -1) >= 0 else "خارج الشبكة",
             "النص": p.text[:120], "الأول": p.post_id == origin.post_id}
            for p in n.cluster.posts
        ])
        color_map = {str(c + 1): community_color(c) for c in range(len(SERIES))}
        color_map["خارج الشبكة"] = OTHER
        fig = px.scatter(df, x="الوقت", y="الصفحة", color="التجمع", color_discrete_map=color_map,
                         hover_data={"النص": True, "الأول": False})
        fig.update_traces(marker=dict(size=11, line=dict(width=2, color="#fcfcfb")))
        first = df[df["الأول"]]
        fig.add_scatter(x=first["الوقت"], y=first["الصفحة"], mode="markers+text", text=["المصدر"],
                        textposition="middle right", showlegend=False, hoverinfo="skip",
                        marker=dict(size=18, symbol="star", color="#0b0b0b"))
        fig.update_layout(height=max(300, 32 * df["الصفحة"].nunique() + 120), plot_bgcolor="#fcfcfb",
                          margin=dict(l=10, r=10, t=10, b=10), legend_title_text="التجمع")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(df.drop(columns=["الأول"]), hide_index=True, width="stretch")

# --- export ----------------------------------------------------------------------

with tab_export:
    name = st.text_input("اسم التحقيق", value=st.session_state.get("inv_name", ""))
    if st.button("💾 حفظ التحقيق", disabled=not name.strip()):
        store().save(name.strip(), inv.to_state())
        st.session_state.inv_name = name.strip()
        st.success("تم الحفظ.")

    ev = evidence_table(inv)
    st.subheader(f"الأدلة ({len(ev)} حدث بين الصفحات المقبولة)")
    st.dataframe(ev, hide_index=True, width="stretch")
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("تقرير JSON", json_report(inv), "report.json", "application/json")
    d2.download_button("الأدلة CSV", ev.to_csv(index=False).encode("utf-8-sig"), "evidence.csv", "text/csv")
    d3.download_button("الصفحات CSV", pages_table(inv).to_csv(index=False).encode("utf-8-sig"), "pages.csv", "text/csv")
    gexf = nx.Graph()
    for n_, d_ in graph.nodes(data=True):
        gexf.add_node(n_, **{k: v for k, v in d_.items() if isinstance(v, (str, int, float))})
    for a_, b_, d_ in graph.edges(data=True):
        gexf.add_edge(a_, b_, kind=d_["kind"], weight=d_["weight"])
    d4.download_button("الشبكة لـ Gephi", "\n".join(nx.generate_gexf(gexf)), "network.gexf", "application/xml")
