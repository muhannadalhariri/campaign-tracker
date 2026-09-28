"""Generate a fully synthetic demo dataset.

Everything here is fictional: page names carry "(تجريبي)", websites use the
reserved `.example` TLD and the rumors concern an imaginary city. The data
contains:

* Network A — 10 pages created within two weeks, pushing three websites that
  share one analytics id, posting links within seconds of each other and
  copy-pasting rumors with small edits.
* Network B — 5 pages with the same behavior on a smaller scale, connected to
  A through two "bridge" pages.
* 25 organic pages posting unrelated content, occasionally sharing the same
  popular links hours apart (which must NOT be flagged).

Run:  python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
rng = random.Random(7)
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)

NET_A_NAMES = [
    "صوت المدينة الحر", "أخبار النخيل العاجلة", "عين على الحدث", "الحقيقة الكاملة",
    "شبكة أخبار الساحل", "نبض الشارع", "المرصد اليومي", "كواليس المدينة",
    "أخبار لحظة بلحظة", "الخبر اليقين",
]
NET_B_NAMES = ["منبر الشباب", "صدى الأحياء", "رأي الناس", "الكلمة الحرة", "بوابة الحي"]
ORGANIC_NAMES = [
    "مطبخ أم سالم", "نادي كرة الساحل", "مكتبة الحي", "عشاق التصوير", "سوق المستعمل",
    "رحلات وطبيعة", "تعليم البرمجة", "أخبار الجامعة", "صيدلية المدينة", "حديقة الأطفال",
    "مجلة الفن", "محبي القهوة", "نادي القراءة", "أخبار الطقس المحلي", "ورشة النجارة",
    "دليل المطاعم", "فريق التطوع", "مهرجان الربيع", "تربية النحل", "مسرح المدينة",
    "أخبار الرياضة", "عيادة الأسنان", "تصميم داخلي", "سينما الحي", "مزرعة الورد",
]

NET_A_DOMAINS = ["alnakheel-now.example", "sahel-truth.example", "city-leaks.example"]
NET_B_DOMAINS = ["youth-voice.example"]
ORGANIC_DOMAINS = ["recipes.example", "football-club.example", "weather-local.example",
                   "uni-news.example", "books-club.example"]

RUMORS_A = [
    "مصادر خاصة تؤكد انقطاع المياه عن كامل أحياء مدينة النخيل لمدة أسبوعين ابتداء من الغد والبلدية تخفي الحقيقة عن السكان",
    "عاجل وثيقة مسربة تكشف أن المستشفى المركزي في مدينة النخيل سيغلق أبوابه نهاية الشهر وسيتم نقل المرضى دون إبلاغ ذويهم",
    "تحذير هام محطات الوقود في مدينة النخيل ستتوقف عن العمل خلال ساعات وعلى الجميع التزود بالوقود فورا قبل فوات الأوان",
    "خبر صادم المجلس البلدي قرر مضاعفة رسوم الكهرباء ثلاث مرات دون أي إعلان رسمي والسكان آخر من يعلم",
    "انتشار مرض غامض في مدارس مدينة النخيل والإدارة تمنع الأهالي من الحديث عنه ويجب سحب الأطفال فورا",
]
RUMORS_B = [
    "شباب المدينة يطالبون بالنزول إلى الساحات بعد تسريب قرار إغلاق الجامعة المحلية نهائيا دون سبب واضح",
    "بيان منسوب لإدارة الجامعة يؤكد إلغاء المنح الدراسية لجميع طلاب مدينة النخيل ابتداء من الفصل القادم",
]
ORGANIC_TEXTS = [
    "وصفة اليوم كعك بالتمر سهل التحضير جربوها وأخبرونا برأيكم",
    "مباراة الأمس كانت رائعة شكرا لكل الجماهير التي حضرت",
    "وصلتنا كتب جديدة هذا الأسبوع ندعوكم لزيارة المكتبة",
    "صورة من غروب الشمس على شاطئ المدينة مساء أمس",
    "للبيع دراجة هوائية بحالة ممتازة التواصل عبر الرسائل",
    "درس جديد في أساسيات بايثون متاح الآن على القناة",
    "توقعات الطقس غدا أجواء معتدلة مع احتمال أمطار خفيفة",
    "فريق التطوع ينظم حملة لتنظيف الحديقة يوم الجمعة",
    "عرض مسرحي جديد يبدأ الأسبوع القادم احجزوا مقاعدكم",
    "افتتاح مطعم جديد في وسط المدينة بأطباق تقليدية",
]
PREFIXES = ["", "عاجل: ", "⚠️ ", "انشر قبل الحذف ", "خطير جدا ", "🔴 "]
SUFFIXES = ["", " #مدينة_النخيل", " #انشر", " شارك ليعرف الجميع", " #الحقيقة"]


def perturb(text: str) -> str:
    """Small edits used to evade exact-match detection."""
    words = text.split()
    if rng.random() < 0.4 and len(words) > 6:
        i = rng.randrange(1, len(words) - 1)
        words[i] = words[i].replace("ا", "ـا", 1)  # tatweel
    if rng.random() < 0.3:
        words.insert(rng.randrange(len(words)), rng.choice(["جدا", "الآن", "رسميا"]))
    text = " ".join(words)
    if rng.random() < 0.3:
        text = text.replace("ة", "ه", 1)
    return rng.choice(PREFIXES) + text + rng.choice(SUFFIXES)


def rand_hash() -> str:
    return f"{rng.getrandbits(64):016x}"


def near_hash(h: str, bits: int) -> str:
    v = int(h, 16)
    for _ in range(bits):
        v ^= 1 << rng.randrange(64)
    return f"{v:016x}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pages, posts = [], []
    counter = iter(range(1, 100000))

    def pid(prefix, i):
        return f"{prefix}{i:02d}"

    net_a = [pid("A", i) for i in range(1, 11)]
    net_b = [pid("B", i) for i in range(1, 6)]
    organic = [pid("O", i) for i in range(1, 26)]
    bridges = [net_a[8], net_a[9]]

    created_a = datetime(2025, 11, 3, tzinfo=timezone.utc)
    for i, p in enumerate(net_a):
        pages.append(dict(page_id=p, name=f"{NET_A_NAMES[i]} (تجريبي)",
                          created_at=(created_a + timedelta(days=rng.randint(0, 13))).date(),
                          admin_countries=rng.choice(["XA", "XA|XB", "XA"]),
                          name_changes=rng.randint(1, 4), followers=rng.randint(8000, 90000),
                          category="News & media website"))
    created_b = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i, p in enumerate(net_b):
        pages.append(dict(page_id=p, name=f"{NET_B_NAMES[i]} (تجريبي)",
                          created_at=(created_b + timedelta(days=rng.randint(0, 10))).date(),
                          admin_countries="XB", name_changes=rng.randint(0, 2),
                          followers=rng.randint(2000, 20000), category="Community"))
    for i, p in enumerate(organic):
        pages.append(dict(page_id=p, name=f"{ORGANIC_NAMES[i]} (تجريبي)",
                          created_at=(datetime(2016, 1, 1, tzinfo=timezone.utc)
                                      + timedelta(days=rng.randint(0, 3000))).date(),
                          admin_countries=rng.choice(["XC", "XD", "XC|XD"]),
                          name_changes=0, followers=rng.randint(300, 40000), category="Local business"))

    def add(page, when, text="", link="", phash="", reactions=None):
        n = next(counter)
        posts.append(dict(
            post_id=f"p{n:05d}", page_id=page, created_at=when.isoformat(),
            text=text, permalink=f"https://www.facebook.com/{page}/posts/{n:05d}",
            links=link, image_phash=phash,
            reactions=reactions if reactions is not None else rng.randint(5, 3000),
            shares=rng.randint(0, 800),
        ))

    def link_burst(members, start, link, text, phash="", max_gap=45):
        """Members post the same link within seconds (tracking params vary)."""
        t = start
        for m in rng.sample(members, k=max(3, int(len(members) * rng.uniform(0.6, 1.0)))):
            variant = link + rng.choice(["", "?utm_source=fb", "?fbclid=Iw" + str(rng.randint(1000, 9999)), "/"])
            add(m, t, perturb(text), variant, near_hash(phash, rng.randint(0, 2)) if phash else "")
            t += timedelta(seconds=rng.randint(3, max_gap))

    def copypasta(members, start, text, phash=""):
        t = start
        for m in rng.sample(members, k=max(3, int(len(members) * rng.uniform(0.5, 0.9)))):
            add(m, t, perturb(text), "", near_hash(phash, rng.randint(0, 3)) if phash else "")
            t += timedelta(minutes=rng.randint(1, 12))

    # Network A: 12 days of link bursts and copy-paste rumors.
    img_a = [rand_hash() for _ in RUMORS_A]
    for day in range(12):
        base = T0 + timedelta(days=day, hours=rng.randint(0, 10))
        dom = rng.choice(NET_A_DOMAINS)
        r = rng.randrange(len(RUMORS_A))
        link_burst(net_a, base, f"https://www.{dom}/news/{2000 + day}", RUMORS_A[r], img_a[r])
        if day % 2 == 0:
            r2 = rng.randrange(len(RUMORS_A))
            copypasta(net_a, base + timedelta(hours=5), RUMORS_A[r2], img_a[r2])

    # Network B, amplified by the two bridge pages.
    for day in range(0, 12, 2):
        base = T0 + timedelta(days=day, hours=14)
        r = rng.randrange(len(RUMORS_B))
        link_burst(net_b + bridges, base, f"https://{NET_B_DOMAINS[0]}/post/{300 + day}", RUMORS_B[r])
        if day % 4 == 0:
            copypasta(net_b + bridges, base + timedelta(hours=3), RUMORS_B[rng.randrange(len(RUMORS_B))])

    # Organic activity, including a genuinely viral link shared hours apart.
    for p in organic + net_a + net_b:
        for _ in range(rng.randint(4, 10)):
            when = T0 + timedelta(minutes=rng.randint(0, 14 * 24 * 60))
            link = ""
            if rng.random() < 0.4:
                link = rng.choice([
                    f"https://{rng.choice(ORGANIC_DOMAINS)}/a/{rng.randint(1, 40)}",
                    "https://www.youtube.com/watch?v=demo" + str(rng.randint(1, 5)),
                    "https://www.bbc.com/arabic/demo-story",
                ])
            add(p, when, rng.choice(ORGANIC_TEXTS), link, rand_hash() if rng.random() < 0.3 else "")
    for i, p in enumerate(rng.sample(organic, 8)):
        add(p, T0 + timedelta(days=3, hours=2 * i + rng.random()), "شاهدوا هذا التقرير الجميل عن مهرجان الربيع",
            "https://festival-news.example/spring-2026")

    posts.sort(key=lambda r: r["created_at"])
    domains = [
        dict(domain=d, tracking_ids="G-DEMO4X1Z7Q|ca-pub-0000000000000001",
             registered_at="2025-10-2" + str(i), registrar="Demo Registrar")
        for i, d in enumerate(NET_A_DOMAINS)
    ] + [
        # Never linked by the pages, but shares the analytics id: found via the id.
        dict(domain="hidden-mirror.example", tracking_ids="G-DEMO4X1Z7Q",
             registered_at="2025-10-25", registrar="Demo Registrar"),
        dict(domain=NET_B_DOMAINS[0], tracking_ids="G-DEMOB2222", registered_at="2026-01-08",
             registrar="Other Registrar"),
    ] + [
        dict(domain=d, tracking_ids=f"G-ORG{i:05d}", registered_at=f"201{i}-05-01", registrar="Various")
        for i, d in enumerate(ORGANIC_DOMAINS)
    ]

    for name, rows in (("posts.csv", posts), ("pages.csv", pages), ("domains.csv", domains)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    seed = next(r for r in posts if r["page_id"] == "A01" and r["links"])
    print(f"{len(pages)} pages, {len(posts)} posts, {len(domains)} domains -> {OUT}")
    print(f"Suggested seed post: {seed['post_id']}  ({seed['permalink']})")


if __name__ == "__main__":
    main()
