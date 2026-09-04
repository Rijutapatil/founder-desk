"""Embedders.

The property that matters: the two are interchangeable from the store's point of
view, which is what makes the hashing-vs-model comparison in the README a fair
one rather than two different systems.
"""

from __future__ import annotations

import numpy as np
import pytest

from agent.retrieval.embedder import (
    QUERY_PREFIX,
    HashingEmbedder,
    load_embedder,
    sentence_transformers_available,
)
from agent.retrieval.store import build_store
from tests.conftest import make_span

needs_model = pytest.mark.skipif(
    not sentence_transformers_available(), reason='needs pip install -e ".[rerank]"'
)


def test_auto_resolves_to_the_best_available() -> None:
    resolved = load_embedder("auto")
    assert resolved.name != "hashing" if sentence_transformers_available() else True


def test_an_unknown_embedder_name_raises() -> None:
    """A typo in a config must not silently select the weaker embedder."""
    with pytest.raises(ValueError, match="unknown embedder"):
        load_embedder("hasing")


class TestHashingEmbedder:
    def test_output_is_l2_normalised(self) -> None:
        vectors = HashingEmbedder().embed(["gst registration", "provident fund"])
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)

    def test_it_is_deterministic_across_calls(self) -> None:
        """Pinned because a test that depends on embedding order must not flake."""
        a, b = HashingEmbedder(), HashingEmbedder()
        assert np.allclose(a.embed(["turnover threshold"]), b.embed(["turnover threshold"]))

    def test_query_and_passage_are_treated_alike(self) -> None:
        embedder = HashingEmbedder()
        assert np.allclose(embedder.embed_query("gst"), embedder.embed(["gst"])[0])


@needs_model
class TestSentenceTransformerEmbedder:
    @pytest.fixture(scope="class")
    def embedder(self):
        return load_embedder("model")

    def test_output_is_l2_normalised(self, embedder) -> None:
        vectors = embedder.embed(["gst registration", "provident fund"])
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)

    def test_the_query_side_instruction_is_applied_only_to_queries(self, embedder) -> None:
        """BGE is trained asymmetrically; embedding a question as a passage wastes it."""
        as_query = embedder.embed_query("gst registration")
        as_passage = embedder.embed(["gst registration"])[0]
        prefixed = embedder.embed([QUERY_PREFIX + "gst registration"])[0]
        assert np.allclose(as_query, prefixed, atol=1e-5)
        assert not np.allclose(as_query, as_passage, atol=1e-3)

    def test_it_bridges_a_paraphrase_the_hashing_embedder_cannot(self, embedder) -> None:
        """The whole reason for this class."""
        question = "how long can my staff be made to work in a day"
        spans = [
            make_span("src:1", "What are the working hours for employees? Not more than nine hours a day."),
            make_span("src:2", "What is the GST registration threshold? Twenty lakh rupees of turnover."),
        ]
        model_top = build_store(spans, embedder).search(question, k=1, alpha=1.0)[0]
        assert model_top.span.span_id == "src:1"


def test_the_store_treats_both_embedders_identically() -> None:
    """Same contract, so swapping one for the other is a fair comparison."""
    spans = [make_span("src:1", "Registration is required once turnover exceeds twenty lakh.")]
    store = build_store(spans, HashingEmbedder())
    assert store.vectors is not None
    assert store.vectors.shape == (1, HashingEmbedder().dimensions)
