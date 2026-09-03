"""The evaluation set itself must stay honest."""

from __future__ import annotations

import pytest

from agent.schema import AnswerKind
from eval.dataset import UnresolvedGold, load_examples, resolve_gold
from ingest.build_corpus import load_spans
from tests.conftest import make_span


def test_every_gold_anchor_resolves_to_exactly_one_span() -> None:
    """The guard against silent relabelling.

    Gold labels reference a phrase from the source question, not a span id. If a
    source is reworded or a parser change drops a span, this fails loudly and
    names the broken label - rather than scoring zero for that question and
    reading as a retrieval regression, which is exactly how the bug that
    motivated this test first appeared.
    """
    spans = load_spans()
    if not spans:
        pytest.skip("no corpus on disk")
    examples = load_examples(spans=spans)
    labelled = [e for e in examples if e.anchor]
    assert labelled, "the grounded section should carry anchors"
    for example in labelled:
        assert example.gold_span, f"unresolved: {example.question}"


def test_an_ambiguous_anchor_is_an_error() -> None:
    """Two matches would make the 'correct' answer arbitrary."""
    from eval.dataset import Example

    spans = [
        make_span("src:1", "registration is required"),
        make_span("src:2", "registration is required too"),
    ]
    example = Example(
        question="q", expected_kind=AnswerKind.GROUNDED, source="src", anchor="registration"
    )
    with pytest.raises(UnresolvedGold, match="matched 2 spans"):
        resolve_gold([example], spans)


def test_a_missing_anchor_is_an_error() -> None:
    from eval.dataset import Example

    example = Example(question="q", expected_kind=AnswerKind.GROUNDED, source="src", anchor="nope")
    with pytest.raises(UnresolvedGold, match="matched 0 spans"):
        resolve_gold([example], [make_span("src:1")])


def test_questions_are_paraphrases_not_copies() -> None:
    """A question copied from its span would measure string matching, not retrieval."""
    spans = load_spans()
    if not spans:
        pytest.skip("no corpus on disk")
    by_id = {s.span_id: s for s in spans}
    for example in load_examples(spans=spans):
        if not example.gold_span:
            continue
        source_question = by_id[example.gold_span].text.partition("\n")[0]
        assert example.question.strip().lower() != source_question.strip().lower(), (
            f"eval question is a verbatim copy of its source: {example.question!r}"
        )


def test_the_set_covers_all_four_outcomes() -> None:
    kinds = {e.expected_kind for e in load_examples(spans=[])}
    assert kinds == set(AnswerKind)
