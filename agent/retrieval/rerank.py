"""Reranking.

Hybrid retrieval is a *bag-of-signals* method: BM25 sees term overlap and the
embedding sees rough topical similarity, but neither reads the query and the
span together. That is exactly what a cross-encoder does - it takes the pair as
one input and scores relevance jointly, which is why it can tell "do traders
under Rs. 20 lakh need to register?" apart from "does a registered trader
dealing in exempt goods need to file returns?" when both share almost every
content word.

The cost is latency and a very large dependency, so this is opt-in and, more
importantly, **measured**. ``eval.runner --compare-rerank`` reports retrieval
quality with and without it on the same questions. A reranker that does not move
the number is latency and 2 GB of wheels for nothing, and should be removed;
this module exists so that judgement can be made from data instead of from the
general reputation of cross-encoders.

The base install deliberately does not include torch. ``CrossEncoderReranker``
raises a clear instruction if constructed without it, rather than silently
degrading - a silent fallback would make the comparison above meaningless, since
"reranked" and "not reranked" would quietly be the same run.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agent.retrieval.store import ScoredSpan

# bge-reranker-base is ~280 MB and English-capable, which suits a corpus of
# Indian government English. A larger reranker is available and slower; the
# eval is the place to decide whether the trade is worth it.
DEFAULT_MODEL = "BAAI/bge-reranker-base"


class Reranker(Protocol):
    """Reorders retrieval hits. Must never invent or drop content, only reorder."""

    @property
    def name(self) -> str: ...

    def rerank(
        self, query: str, hits: Sequence[ScoredSpan], k: int | None = None
    ) -> list[ScoredSpan]: ...


class IdentityReranker:
    """No-op. The control arm of the comparison, and the default everywhere torch is absent."""

    @property
    def name(self) -> str:
        return "identity"

    def rerank(
        self, query: str, hits: Sequence[ScoredSpan], k: int | None = None
    ) -> list[ScoredSpan]:
        return list(hits[:k] if k else hits)


class CrossEncoderReranker:
    """Cross-encoder reranking over the first-stage candidates.

    Retrieve wide, rerank narrow: the store is asked for more candidates than
    the answer needs, and the cross-encoder chooses among them. Reranking cannot
    recover a span the first stage never returned, so the candidate pool is the
    ceiling on what this can achieve - which is why ``top_k`` at retrieval time
    matters as much as the reranker itself.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, *, batch_size: int = 16) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise ImportError(
                "CrossEncoderReranker needs the optional reranking extra. "
                'Install it with: pip install -e ".[rerank]"'
            ) from exc
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = CrossEncoder(model_name)

    @property
    def name(self) -> str:
        return f"cross-encoder:{self._model_name}"

    def rerank(
        self, query: str, hits: Sequence[ScoredSpan], k: int | None = None
    ) -> list[ScoredSpan]:
        if not hits:
            return []
        scores = self._model.predict(
            [(query, hit.span.text) for hit in hits], batch_size=self._batch_size
        )
        rescored = [
            hit.model_copy(update={"rerank_score": float(score)})
            for hit, score in zip(hits, scores, strict=True)
        ]
        rescored.sort(key=lambda h: h.rerank_score or 0.0, reverse=True)
        return rescored[:k] if k else rescored


def cross_encoder_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def best_available_reranker() -> Reranker:
    """The cross-encoder if it is installed, otherwise the no-op.

    The choice is not only about ranking quality. The answering layer gates
    refusals on the cross-encoder's score when it has one, and that gate is
    measurably better than the lexical fallback (refusal accuracy 0.692 against
    0.385). So an install without the extra is a materially weaker system, and
    the CLI says so rather than letting the difference go unnoticed.
    """
    return CrossEncoderReranker() if cross_encoder_available() else IdentityReranker()


def load_reranker(name: str = "identity") -> Reranker:
    """Resolve a reranker by name. Unknown names raise rather than defaulting.

    Defaulting an unrecognised name to identity would let a typo in a CI config
    silently turn the reranker off and report the result as if it were on.
    """
    if name == "auto":
        return best_available_reranker()
    if name == "identity":
        return IdentityReranker()
    if name in ("cross-encoder", "cross_encoder"):
        return CrossEncoderReranker()
    raise ValueError(f"unknown reranker: {name!r} (expected 'auto', 'identity' or 'cross-encoder')")
