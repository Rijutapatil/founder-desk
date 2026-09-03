"""Hybrid retrieval, and the signal that lets the system refuse."""

from __future__ import annotations

from agent.retrieval.store import build_store, tokenize
from tests.conftest import make_span

CORPUS = [
    make_span(
        "src:1",
        "Do I need GST registration? Registration is required once aggregate turnover exceeds twenty lakh rupees.",
    ),
    make_span(
        "src:2",
        "What is form INC-20A? A declaration of commencement of business filed with the registrar.",
    ),
    make_span(
        "src:3",
        "How much provident fund must an employer contribute? Twelve percent of basic wages and dearness allowance.",
    ),
    make_span(
        "src:4",
        "Can an apprentice join the provident fund scheme? An apprentice is not treated as an employee for this purpose.",
    ),
]


def test_lexical_half_finds_exact_terms() -> None:
    """The reason retrieval is hybrid: a dense vector blurs 'INC-20A'."""
    store = build_store(CORPUS)
    assert store.search("INC-20A", k=1)[0].span.span_id == "src:2"


def test_vector_half_bridges_paraphrase() -> None:
    store = build_store(CORPUS)
    top = store.search("how much does an employer put into PF", k=2)
    assert "src:3" in {h.span.span_id for h in top}


def test_where_filters_before_scoring() -> None:
    store = build_store(CORPUS)
    hits = store.search("registration", k=4, where=lambda s: s.span_id == "src:2")
    assert [h.span.span_id for h in hits] == ["src:2"]


def test_empty_filter_returns_nothing_rather_than_everything() -> None:
    store = build_store(CORPUS)
    assert store.search("registration", where=lambda s: False) == []


class TestQueryCoverage:
    """The refusal signal.

    ``score`` is min-max normalised, so the top hit is ~1.0 even for nonsense -
    which is exactly why the gate is coverage instead. These tests pin the
    property that made the difference.
    """

    def test_normalised_score_cannot_distinguish_nonsense(self) -> None:
        store = build_store(CORPUS)
        top = store.search("who won the football match", k=1)
        assert top and top[0].score > 0.9  # a confident number for an unanswerable query

    def test_coverage_is_high_for_an_on_topic_question(self) -> None:
        store = build_store(CORPUS)
        best = max(
            h.query_coverage for h in store.search("provident fund employer contribution", k=4)
        )
        assert best > 0.5

    def test_coverage_is_low_for_an_off_topic_question(self) -> None:
        store = build_store(CORPUS)
        best = max(h.query_coverage for h in store.search("who won the football match", k=4))
        assert best < 0.3

    def test_idf_weighting_beats_plain_word_overlap(self) -> None:
        """Sharing a common word must not look like relevance.

        "registration" appears throughout the corpus and carries little
        information; a query whose only overlap is a term like that should score
        low, which plain proportional coverage would not deliver.
        """
        store = build_store(CORPUS)
        best = max(
            h.query_coverage for h in store.search("trademark registration for a logo design", k=4)
        )
        assert best < 0.5


def test_tokenizer_keeps_alphanumerics_together() -> None:
    assert tokenize("Form INC-20A, Rs.15,000") == ["form", "inc", "20a", "rs", "15", "000"]
