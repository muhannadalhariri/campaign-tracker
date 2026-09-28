"""Text and URL normalization.

Arabic text is normalized so that trivial edits (diacritics, tatweel, letter
variants) used to evade copy-paste detection do not hide near-duplicates.
URLs are canonicalized so the same article shared with different tracking
parameters or mobile subdomains counts as the same link.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_URL_RE = re.compile(r"https?://[^\s<>\"'،]+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#([\w؀-ۿ]+)")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

_ARABIC_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
        # Eastern Arabic digits -> ASCII
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    }
)

TRACKING_PARAMS = {
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
    "s", "si", "feature", "_rdr", "mibextid",
}

# Subdomains that point at the same site as the bare domain.
_EQUIVALENT_PREFIXES = ("www.", "m.", "mobile.", "amp.", "l.", "lm.")


def normalize_text(text: str | None) -> str:
    """Normalize Arabic/Latin text for similarity comparison."""
    if not text:
        return ""
    text = _URL_RE.sub(" ", str(text))
    text = _DIACRITICS.sub("", text).replace(_TATWEEL, "")
    text = text.translate(_ARABIC_MAP).lower()
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return [u.rstrip(".,;:!?)]}") for u in _URL_RE.findall(str(text))]


def extract_hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    return sorted({normalize_text(h) for h in _HASHTAG_RE.findall(str(text))} - {""})


def domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    for prefix in _EQUIVALENT_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    return host


def canonical_url(url: str | None) -> str:
    """Canonical form of a URL: no scheme, no tracking params, no fragment."""
    if not url:
        return ""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = domain_of(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/") or ""
    return urlunsplit(("", host, path, urlencode(sorted(query)), "")).lstrip("/")


def split_multi(value) -> list[str]:
    """Split a multi-valued CSV cell (pipe, comma or whitespace separated)."""
    if value is None:
        return []
    if isinstance(value, float):  # NaN from pandas
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p for p in re.split(r"[|,\s]+", str(value).strip()) if p]
