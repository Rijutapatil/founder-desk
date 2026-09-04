"""State law: ask only when it helps, and never imply a state that was not used.

The bug these pin: the system asked "which state is the registered office in?",
took "Maharashtra", answered from the *central* Contract Labour Act, and stamped
the result `state: MH`. Zero of 499 spans carried a state scope, so the state was
collected, ignored, and then advertised.
"""

from __future__ import annotations

import pytest

from agent.answerer import Answerer, build_answerer
from agent.retrieval.store import build_store
from agent.schema import AnswerKind
from ingest.build_corpus import load_spans
from sources.loader import load_allowlist
from tests.conftest import make_span

needs_corpus = pytest.mark.skipif(not load_spans(), reason="no corpus on disk")


@pytest.fixture(scope="module")
def answerer():
    return build_answerer()


@needs_corpus
class TestStateAnswers:
    def test_the_corpus_actually_holds_state_scoped_spans(self, answerer) -> None:
        """Without this the whole state mechanism is decorative."""
        assert answerer.covered_states, "no state-scoped sources: the clarify path is a dead end"

    def test_a_covered_state_is_answered_from_that_state(self, answerer) -> None:
        answer = answerer.answer("which part of Delhi does the shops and establishments law cover")
        assert answer.kind is AnswerKind.GROUNDED
        assert any(s.span_id.startswith("delhi") for s in answer.cited_spans)

    def test_an_uncovered_state_is_refused_and_named(self, answerer) -> None:
        answer = answerer.answer("do I need shops and establishment registration in Maharashtra")
        assert answer.kind is AnswerKind.REFUSED
        assert any("nothing for MH" in line for line in answer.searched)

    def test_a_state_law_answer_never_rests_only_on_central_law(self, answerer) -> None:
        """The exact defect: a state-stamped answer built from all-India spans."""
        answer = answerer.answer("do I need shops and establishment registration in Karnataka")
        assert answer.kind is not AnswerKind.GROUNDED

    def test_the_clarifying_question_names_the_states_it_can_use(self, answerer) -> None:
        answer = answerer.answer("do I need shops and establishment registration")
        assert answer.kind is AnswerKind.CLARIFY
        assert "DL" in (answer.clarifying_question or "")


class TestNoStateSourcesAtAll:
    """A corpus with no state coverage must not ask a question it cannot use."""

    @pytest.fixture
    def stateless(self) -> Answerer:
        spans = [
            make_span(
                "src:1", "Do I need GST registration? Registration is required over twenty lakh."
            ),
            make_span("src:2", "What is provident fund? Twelve percent of basic wages and DA."),
        ]
        return Answerer(build_store(spans), load_allowlist())

    def test_it_refuses_instead_of_asking(self, stateless) -> None:
        answer = stateless.answer("do I need shops and establishment registration")
        assert answer.kind is AnswerKind.REFUSED
        assert not stateless.covered_states
        assert any("no state" in line for line in answer.searched)

    def test_the_refusal_says_it_holds_no_state_sources(self, stateless) -> None:
        answer = stateless.answer("is professional tax applicable to my company in Delhi")
        assert answer.kind is AnswerKind.REFUSED
        assert any("state-specific sources held" in line for line in answer.searched)


@needs_corpus
class TestStratifiedRetrieval:
    def test_a_states_own_spans_reach_the_reranker(self, answerer) -> None:
        """30 Delhi spans against 529 overall: a single ranked search buries them.

        This is arithmetic, not relevance - which is why the state's corpus is
        retrieved as its own stratum rather than being left to compete on
        first-stage score.
        """
        from agent.router import route

        question = "how long can my staff in Delhi be made to work in a day"
        candidates = answerer.candidates(question, route(question))
        assert any(hit.span.states for hit in candidates)

    def test_stratification_is_skipped_for_uncovered_states(self, answerer) -> None:
        from agent.router import route

        question = "do I need GST registration in Karnataka"
        candidates = answerer.candidates(question, route(question))
        assert not any("KA" in hit.span.states for hit in candidates)
