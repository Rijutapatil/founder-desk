"""The four outcomes, on the real corpus.

These run against the built corpus rather than a fixture, because the behaviour
under test is a property of the whole system - "does it refuse when it should" is
not meaningful against three hand-written spans.
"""

from __future__ import annotations

import pytest

from agent.answerer import build_answerer
from agent.schema import AnswerKind
from ingest.build_corpus import load_spans

pytestmark = pytest.mark.skipif(
    not load_spans(), reason="no corpus on disk (run python -m ingest.build_corpus)"
)


@pytest.fixture(scope="module")
def answerer():
    return build_answerer()


def test_a_covered_question_is_answered_and_cited(answerer) -> None:
    answer = answerer.answer("can a one person company get startup india benefits")
    assert answer.kind is AnswerKind.GROUNDED
    assert answer.cited_spans
    assert "One Person Compan" in answer.claims[0].text


def test_every_claim_quotes_a_cited_span(answerer) -> None:
    answer = answerer.answer("what documents are needed for DPIIT recognition")
    cited = {s.span_id for s in answer.cited_spans}
    for claim in answer.claims:
        assert set(claim.supported_by) <= cited


@pytest.mark.parametrize(
    "question",
    [
        "how do I train a neural network",
        "who won the cricket world cup",
        "how do I get an FSSAI licence",
    ],
)
def test_uncovered_questions_are_refused_not_guessed(answerer, question: str) -> None:
    answer = answerer.answer(question)
    assert answer.kind is AnswerKind.REFUSED
    assert answer.searched, "a refusal must be auditable"
    assert not answer.claims


def test_incorporation_is_refused_because_the_source_is_blocked(answerer) -> None:
    """The valuable refusal: a plausible span exists and must not be used.

    MCA blocks automated collection, so nothing in the corpus covers INC-20A -
    but GST and PF spans about deadlines retrieve happily. Answering from one of
    those would be a confident, correctly-cited, wrong answer.
    """
    assert answerer.answer("by when must I file INC-20A").kind is AnswerKind.REFUSED


def test_state_dependent_question_asks_instead_of_assuming(answerer) -> None:
    answer = answerer.answer("do I need shops and establishment registration")
    assert answer.kind is AnswerKind.CLARIFY
    assert "state" in (answer.clarifying_question or "").lower()


def test_a_recommendation_request_gets_factors_not_a_recommendation(answerer) -> None:
    answer = answerer.answer("should I register an LLP or a Pvt Ltd")
    assert answer.kind is AnswerKind.INFORMATIONAL_ONLY
    assert answer.considerations
    assert not answer.claims
    joined = " ".join(answer.considerations).lower()
    assert "chartered accountant" in joined


def test_answers_do_not_trail_irrelevant_citations(answerer) -> None:
    """One well-matched span beats four, three of which answer other questions."""
    answer = answerer.answer("can a one person company get startup india benefits")
    assert len(answer.cited_spans) <= 2


def test_the_disclaimer_is_always_present(answerer) -> None:
    for question in ["can an OPC get startup india benefits", "who won the world cup"]:
        assert "NOT PROFESSIONAL ADVICE" in answerer.answer(question).disclaimer
