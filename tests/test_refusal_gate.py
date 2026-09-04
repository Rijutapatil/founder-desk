"""The refusal gate.

The gate decides whether the corpus can answer at all, and it is the behaviour
this project is most easily wrong about: a wrong refusal costs a rephrase, a
wrong answer about a filing deadline costs a penalty.

Two implementations, and the difference between them is measured rather than
assumed. See MIN_RELEVANCE in agent/answerer.py for the sweep.
"""

from __future__ import annotations

import pytest

from agent.answerer import MIN_COVERAGE, MIN_RELEVANCE, build_answerer
from agent.retrieval.rerank import (
    CrossEncoderReranker,
    IdentityReranker,
    best_available_reranker,
    cross_encoder_available,
    load_reranker,
)
from agent.schema import AnswerKind
from ingest.build_corpus import load_spans

needs_corpus = pytest.mark.skipif(not load_spans(), reason="no corpus on disk")
needs_cross_encoder = pytest.mark.skipif(
    not cross_encoder_available(), reason='needs the reranking extra: pip install -e ".[rerank]"'
)


def test_auto_resolves_to_the_best_available() -> None:
    resolved = load_reranker("auto")
    if cross_encoder_available():
        assert resolved.name.startswith("cross-encoder")
    else:
        assert resolved.name == "identity"


def test_an_unknown_reranker_name_still_raises() -> None:
    """A typo in CI config must not silently select the weaker gate."""
    with pytest.raises(ValueError, match="unknown reranker"):
        load_reranker("cross_encodr")


def test_best_available_never_returns_none() -> None:
    assert best_available_reranker().name


def test_thresholds_are_the_swept_values() -> None:
    """Pinned so a casual edit shows up as a test change, not a silent behaviour change."""
    assert MIN_COVERAGE == 0.28
    assert MIN_RELEVANCE == 0.05


@needs_corpus
@needs_cross_encoder
class TestCrossEncoderGate:
    @pytest.fixture(scope="class")
    def answerer(self):
        return build_answerer(CrossEncoderReranker())

    @pytest.mark.parametrize(
        "question",
        [
            # The case that motivated this gate. Both phrasings ask the same
            # unanswerable thing; the lexical gate refused the first and
            # answered the second with a definition of a term sheet.
            "How much does it cost to register a trademark for a logo in India?",
            "how much does it cost to trademark a logo in India",
            "who won the cricket world cup",
            "how do I train a neural network on a small dataset",
            "what is the visa process for bringing a foreign director to India",
        ],
    )
    def test_rephrasing_does_not_defeat_the_gate(self, answerer, question: str) -> None:
        assert answerer.answer(question).kind is AnswerKind.REFUSED

    @pytest.mark.parametrize(
        "question",
        [
            "can a one person company get startup india benefits",
            "do traders under 20 lakh turnover need GST registration",
            "at how many contract workers must my establishment register",
            "which kinds of company can I set up in India",
            "does an apprentice have to be enrolled in provident fund",
        ],
    )
    def test_covered_questions_are_still_answered(self, answerer, question: str) -> None:
        assert answerer.answer(question).kind is AnswerKind.GROUNDED

    def test_the_gate_uses_the_rerank_score(self, answerer) -> None:
        from agent.router import route

        question = "can a one person company get startup india benefits"
        ranked = answerer.retrieve(question, route(question))
        assert ranked and ranked[0].rerank_score is not None


@needs_corpus
class TestLexicalFallback:
    """Without the extra the system still works - measurably less well at refusing."""

    @pytest.fixture(scope="class")
    def answerer(self):
        return build_answerer(IdentityReranker())

    def test_clearly_off_topic_is_still_refused(self, answerer) -> None:
        assert answerer.answer("how do I train a neural network").kind is AnswerKind.REFUSED

    def test_covered_questions_are_still_answered(self, answerer) -> None:
        answer = answerer.answer("can a one person company get startup india benefits")
        assert answer.kind is AnswerKind.GROUNDED

    def test_no_rerank_score_means_the_lexical_path_ran(self, answerer) -> None:
        from agent.router import route

        ranked = answerer.retrieve(
            "gst registration threshold", route("gst registration threshold")
        )
        assert all(h.rerank_score is None for h in ranked)
