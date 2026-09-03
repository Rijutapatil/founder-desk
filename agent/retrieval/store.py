"""Hybrid retrieval over the span corpus.

Exact brute-force search over an in-memory matrix. At this corpus size - a few
hundred to a few thousand spans - a numpy matmul is well under a millisecond,
which is an order of magnitude faster than a single network round trip to a
hosted vector database *and* exact where an HNSW index would be approximate.
There is nothing to gain from a database here and latency, cost and an operational
dependency to lose.

Retrieval is **hybrid**, and for this corpus that is not a refinement. Compliance
questions turn on exact tokens - a form number ("INC-20A"), a section reference
("Section 2(6)"), a threshold ("20 lakhs"). A dense embedding blurs precisely
those, while BM25 nails them; conversely BM25 misses that "do I need to register"
and "is registration required" are the same question. Each half covers the
other's failure.

``where`` filters *before* scoring. That is what lets the answering layer
restrict retrieval to spans that actually govern the asker's state and entity
type, rather than ranking everything and hoping the inapplicable ones score low.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import Final

import numpy as np
from pydantic import BaseModel, ConfigDict

from agent.retrieval.embedder import Embedder, HashingEmbedder
from agent.schema import SourceSpan

_TOKEN: Final = re.compile(r"[a-z0-9]+")
# BM25 defaults. k1 damps term-frequency saturation, b controls length
# normalisation. Standard values, untuned - and not worth tuning before there is
# an eval to tune against.
_K1: Final = 1.5
_B: Final = 0.75

# Removed before measuring query coverage. These carry no topical signal, and
# leaving them in would let "do I need to ... for my ..." match anything, which
# is exactly the failure the coverage test exists to catch.
_STOPWORDS: Final = frozenset(
    """a an the and or but if is are was were be been being do does did doing have has had
    having i me my we our you your it its this that these those to of in on for with as at
    by from about into over under again then than so no not can could should would will
    shall may might must need needs required require what when where which who whom how why
    any some all each other more most such only own same too very just also there here""".split()
)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class ScoredSpan(BaseModel):
    """A retrieval hit, with both halves of the score kept separate.

    Keeping the components is not diagnostics for its own sake: when a wrong
    span is retrieved, whether it won on lexical or vector score says which half
    to fix, and the eval reports the split.
    """

    model_config = ConfigDict(frozen=True)

    span: SourceSpan
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0
    rerank_score: float | None = None

    raw_lexical: float = 0.0
    """Unnormalised BM25. Kept because ``score`` cannot answer "is this any good".

    Min-max normalisation makes the ranking readable but destroys absolute
    relevance: the best span in a set of terrible spans still scores 1.0. A
    system that must be able to *refuse* needs a signal that stays small when
    nothing matches, and this is it."""

    query_coverage: float = 0.0
    """Fraction of the query's content words that appear in this span.

    The blunt, interpretable half of the refusal test. A question about capital
    gains on a house scores near zero against a corpus of GST and PF spans, no
    matter which span happens to rank first."""


class SpanStore:
    """Exact hybrid search over an in-memory span corpus."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder if embedder is not None else HashingEmbedder()
        self._spans: list[SourceSpan] = []
        self._matrix: np.ndarray | None = None
        # Inverted index rather than a per-term scan over every document: BM25
        # only touches documents containing the term, so scoring cost follows
        # the postings lists instead of the corpus size.
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._doc_terms: list[frozenset[str]] = []
        self._doc_len: list[int] = []
        self._avg_len: float = 0.0

    def __len__(self) -> int:
        return len(self._spans)

    @property
    def spans(self) -> list[SourceSpan]:
        return list(self._spans)

    def add(self, spans: Sequence[SourceSpan], vectors: np.ndarray | None = None) -> None:
        if not spans:
            return
        if vectors is None:
            vectors = self._embedder.embed([s.text for s in spans])

        base = len(self._spans)
        self._spans.extend(spans)
        for offset, span in enumerate(spans):
            counts = Counter(tokenize(span.text))
            for term, tf in counts.items():
                self._postings[term].append((base + offset, tf))
            self._doc_terms.append(frozenset(counts))
            self._doc_len.append(sum(counts.values()))
        self._avg_len = sum(self._doc_len) / len(self._doc_len)

        block = _l2_normalize(np.asarray(vectors, dtype=np.float32))
        self._matrix = block if self._matrix is None else np.vstack([self._matrix, block])

    def _bm25(self, query: str) -> np.ndarray:
        scores = np.zeros(len(self._spans), dtype=np.float32)
        n = len(self._spans)
        for term in set(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = math.log(1 + (n - len(postings) + 0.5) / (len(postings) + 0.5))
            for idx, tf in postings:
                norm = 1 - _B + _B * (self._doc_len[idx] / (self._avg_len or 1))
                scores[idx] += idf * (tf * (_K1 + 1)) / (tf + _K1 * norm)
        return scores

    def _coverage(self, query: str) -> np.ndarray:
        """Per-span share of the query's *information* that the span contains.

        Weighted by IDF, not a plain word count, and the difference decides real
        cases. "What is the capital gains tax on selling a house" shares two of
        its five content words - "tax" and "selling" - with a GST span about
        e-commerce traders, so plain coverage scores it 0.40 and lets an
        out-of-scope question through. But "capital", "gains" and "house" are the
        words carrying the question's meaning, and they appear nowhere in the
        corpus.

        Terms absent from the corpus entirely get the maximum IDF, which is the
        behaviour we want: a query built from words this corpus has never seen
        should score near zero however many stopword-ish terms it happens to
        share.
        """
        terms = {t for t in tokenize(query) if t not in _STOPWORDS and len(t) > 2}
        if not terms:
            return np.zeros(len(self._spans), dtype=np.float32)

        n = len(self._spans)
        weights = {
            term: math.log(
                1
                + (n - len(self._postings.get(term, ())) + 0.5)
                / (len(self._postings.get(term, ())) + 0.5)
            )
            for term in terms
        }
        total = sum(weights.values())
        if total <= 0:
            return np.zeros(n, dtype=np.float32)
        return np.array(
            [sum(weights[t] for t in terms & doc) / total for doc in self._doc_terms],
            dtype=np.float32,
        )

    def search(
        self,
        query: str,
        k: int = 8,
        *,
        alpha: float = 0.5,
        where: Callable[[SourceSpan], bool] | None = None,
    ) -> list[ScoredSpan]:
        """Hybrid search. ``alpha`` weights vector against lexical (1.0 = vector only)."""
        if not self._spans:
            return []

        mask = (
            np.array([where(s) for s in self._spans], dtype=bool)
            if where is not None
            else np.ones(len(self._spans), dtype=bool)
        )
        if not mask.any():
            return []

        raw_lexical = self._bm25(query)
        lexical = _minmax(raw_lexical)
        coverage = self._coverage(query)
        if self._matrix is not None:
            qv = _l2_normalize(self._embedder.embed([query]).reshape(1, -1))[0]
            vector = _minmax(self._matrix @ qv)
        else:  # pragma: no cover - a store is never built without vectors
            vector, alpha = np.zeros(len(self._spans), dtype=np.float32), 0.0

        combined = np.where(mask, alpha * vector + (1 - alpha) * lexical, -np.inf)
        top = np.argsort(-combined)[: min(k, int(mask.sum()))]
        return [
            ScoredSpan(
                span=self._spans[i],
                score=float(combined[i]),
                vector_score=float(vector[i]),
                lexical_score=float(lexical[i]),
                raw_lexical=float(raw_lexical[i]),
                query_coverage=float(coverage[i]),
            )
            for i in top
            if np.isfinite(combined[i])
        ]


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    result: np.ndarray = matrix / np.where(norms == 0, 1, norms)
    return result


def _minmax(scores: np.ndarray) -> np.ndarray:
    """Scale to [0, 1] so the two halves are comparable.

    Cosine similarity and BM25 live on different scales; combining them raw
    would let BM25 dominate purely by magnitude rather than by relevance.
    """
    lo, hi = float(scores.min()), float(scores.max())
    if hi - lo < 1e-9:
        return np.zeros_like(scores)
    result: np.ndarray = (scores - lo) / (hi - lo)
    return result


def build_store(spans: Sequence[SourceSpan], embedder: Embedder | None = None) -> SpanStore:
    store = SpanStore(embedder)
    store.add(spans)
    return store
