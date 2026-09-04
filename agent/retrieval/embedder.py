"""Embedders.

Two implementations behind one protocol, and the choice between them is the
difference between a system that can bridge a paraphrase and one that cannot.

``HashingEmbedder`` is character n-gram feature hashing: deterministic, offline,
free, and semantically blind. It cannot know that "how long can my staff work in
a day" is asking what "what are the working hours for employees" answers. It
remains the fallback because it needs nothing installed, which is what lets the
free CI gate exercise the whole retrieval path on every pull request.

``SentenceTransformerEmbedder`` is a real embedding model, and it is the default
whenever the reranking extra is installed - it needs no new dependency, because
``sentence-transformers`` is already there for the cross-encoder. It is still
local, still offline after the first download, and still costs nothing per query.
There is no generative model here and none is wanted: this changes which spans
are *found*, never what is said about them, so the guarantee that a claim is a
verbatim quote is untouched.

**Asymmetric retrieval.** BGE models are trained with a short instruction on the
query side only. Embedding a question exactly like a passage measurably wastes
the model, so ``embed_query`` exists alongside ``embed`` and the store calls the
right one. The hashing embedder treats them identically, which is correct for it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final, Protocol

import numpy as np

_HASH_DIMS: Final = 512
_NGRAM: Final = 4


class Embedder(Protocol):
    """Produces L2-normalised embeddings, so cosine reduces to a dot product."""

    @property
    def name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a question. Separate from ``embed`` because some models want a
        query-side instruction that must not be applied to passages."""
        ...


class HashingEmbedder:
    """Deterministic character-n-gram feature hashing."""

    def __init__(self, dimensions: int = _HASH_DIMS, ngram: int = _NGRAM) -> None:
        self._dims = dimensions
        self._ngram = ngram

    @property
    def name(self) -> str:
        return "hashing"

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_query(self, text: str) -> np.ndarray:
        """No query/passage distinction: this model has no notion of either."""
        vector: np.ndarray = self.embed([text])[0]
        return vector

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dims), dtype=np.float32)
        for row, text in enumerate(texts):
            norm = " ".join(text.lower().split())
            for i in range(max(len(norm) - self._ngram + 1, 0)):
                gram = norm[i : i + self._ngram].encode()
                # blake2b rather than hash(): Python's str hash is salted per
                # process, which would make vectors non-reproducible.
                digest = hashlib.blake2b(gram, digest_size=8).digest()
                out[row, int.from_bytes(digest, "big") % self._dims] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        result: np.ndarray = out / np.where(norms == 0, 1, norms)
        return result


# Small, strong, and English. 384 dimensions keeps the whole corpus matrix at a
# few megabytes, so the "no vector database" argument survives the upgrade.
DEFAULT_MODEL: Final = "BAAI/bge-small-en-v1.5"
# BGE's query-side instruction. Applied to questions only - putting it on
# passages too would collapse the asymmetry the model was trained with.
QUERY_PREFIX: Final = "Represent this sentence for searching relevant passages: "


class SentenceTransformerEmbedder:
    """A real embedding model, run locally.

    Loaded once and reused. Encoding is normalised at source so the store's dot
    product is a cosine, matching the hashing embedder's contract exactly - the
    two are interchangeable from the store's point of view, which is what makes
    the A/B comparison in the README a fair one.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, *, batch_size: int = 32) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise ImportError(
                "SentenceTransformerEmbedder needs the optional reranking extra. "
                'Install it with: pip install -e ".[rerank]"'
            ) from exc
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = SentenceTransformer(model_name)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        dims = self._model.get_sentence_embedding_dimension()
        # sentence-transformers types this as optional; every model this project
        # can load reports one, and a None here means the model is unusable.
        if dims is None:  # pragma: no cover - would mean a broken model
            raise RuntimeError(f"{self._model_name} reports no embedding dimension")
        return int(dims)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors: np.ndarray = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        vector: np.ndarray = self.embed([QUERY_PREFIX + text])[0]
        return vector


def sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def best_available_embedder() -> Embedder:
    """The real model if it is installed, the hashing fallback otherwise."""
    return SentenceTransformerEmbedder() if sentence_transformers_available() else HashingEmbedder()


def load_embedder(name: str = "auto") -> Embedder:
    """Resolve by name. Unknown names raise rather than silently degrading."""
    if name == "auto":
        return best_available_embedder()
    if name == "hashing":
        return HashingEmbedder()
    if name in ("sentence-transformer", "model"):
        return SentenceTransformerEmbedder()
    raise ValueError(f"unknown embedder: {name!r} (expected 'auto', 'hashing' or 'model')")
