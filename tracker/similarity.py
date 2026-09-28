"""Near-duplicate detection for text and images."""

from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .normalize import normalize_text

# Very short texts ("شاهد", "عاجل") collide trivially; ignore them.
MIN_TEXT_CHARS = 25


def hamming_hex(a: str, b: str) -> int:
    """Bit distance between two hex-encoded perceptual hashes."""
    if not a or not b or len(a) != len(b):
        return 10**6
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 10**6


def _vectorizer() -> TfidfVectorizer:
    # Character n-grams within word boundaries are robust to Arabic
    # morphology and to small edits, and need no language model.
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)


def similar_pairs(texts: list[str], threshold: float) -> list[tuple[int, int, float]]:
    """All index pairs (i < j) whose normalized texts have cosine >= threshold."""
    norm = [normalize_text(t) for t in texts]
    idx = [i for i, t in enumerate(norm) if len(t) >= MIN_TEXT_CHARS]
    if len(idx) < 2:
        return []
    matrix = _vectorizer().fit_transform([norm[i] for i in idx])
    sims = (matrix @ matrix.T).tocoo()
    pairs = []
    for r, c, v in zip(sims.row, sims.col, sims.data):
        if r < c and v >= threshold:
            pairs.append((idx[r], idx[c], float(v)))
    return pairs


class TextIndex:
    """Pre-vectorized corpus for repeated "find near-duplicates of X" queries."""

    def __init__(self, texts: list[str]):
        self._norm = [normalize_text(t) for t in texts]
        self._usable = np.array([len(t) >= MIN_TEXT_CHARS for t in self._norm], dtype=bool)
        self._vec = _vectorizer()
        self._matrix = self._vec.fit_transform(self._norm) if self._norm else None

    def query(self, text: str, threshold: float) -> list[tuple[int, float]]:
        q = normalize_text(text)
        if self._matrix is None or len(q) < MIN_TEXT_CHARS:
            return []
        scores = (self._matrix @ self._vec.transform([q]).T).toarray().ravel()
        hits = np.nonzero((scores >= threshold) & self._usable)[0]
        return [(int(i), float(scores[i])) for i in hits]
