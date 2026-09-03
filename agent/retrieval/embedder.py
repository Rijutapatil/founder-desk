"""Embedders.

Two implementations behind one protocol. The default is deterministic, offline
and free, which is a deliberate architectural choice rather than a placeholder:
it means retrieval quality is measurable in CI on every pull request, with no
API key, no billing and no network. A gate that costs money to run is a gate
someone eventually disables.

``HashingEmbedder`` uses character n-gram feature hashing. It is not
semantically clever - it will not know that "turnover" and "revenue" are related
- but the lexical half of hybrid search covers exact legal terms, and being
stable across processes and machines is worth more here than cleverness, because
a test that depends on embedding order must not flake.
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
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class HashingEmbedder:
    """Deterministic character-n-gram feature hashing."""

    def __init__(self, dimensions: int = _HASH_DIMS, ngram: int = _NGRAM) -> None:
        self._dims = dimensions
        self._ngram = ngram

    @property
    def dimensions(self) -> int:
        return self._dims

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
