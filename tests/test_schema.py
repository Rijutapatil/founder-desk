"""The output contract. These tests are the guarantee, not the prompt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent.schema import (
    DISCLAIMER,
    Answer,
    AnswerKind,
    AuthorityTier,
    CitedSpan,
    Claim,
    SpanStatus,
)
from tests.conftest import NOW, make_span


def _cited() -> CitedSpan:
    return CitedSpan.of(make_span())


def test_a_claim_cannot_exist_without_support() -> None:
    with pytest.raises(ValueError, match="ungrounded claim"):
        Claim(text="You must register within 30 days.", supported_by=())


def test_grounded_answer_requires_a_citation() -> None:
    with pytest.raises(ValueError, match="must quote a source"):
        Answer(
            kind=AnswerKind.GROUNDED,
            question="q",
            claims=(Claim(text="x", supported_by=("src:a",)),),
        )


def test_citing_a_span_that_is_not_in_cited_spans_is_fabrication() -> None:
    """The core guarantee: a claim cannot point at authority the answer never carried."""
    with pytest.raises(ValueError, match="fabricated citation"):
        Answer(
            kind=AnswerKind.GROUNDED,
            question="q",
            claims=(Claim(text="x", supported_by=("src:never-retrieved",)),),
            cited_spans=(_cited(),),
        )


def test_a_valid_grounded_answer_is_constructible() -> None:
    answer = Answer(
        kind=AnswerKind.GROUNDED,
        question="q",
        claims=(Claim(text="Yes, you do.", supported_by=("src:a",)),),
        cited_spans=(_cited(),),
    )
    assert answer.claims[0].supported_by == ("src:a",)


def test_disclaimer_cannot_be_removed_or_reworded() -> None:
    answer = Answer(
        kind=AnswerKind.REFUSED, question="q", searched=("CBIC",), disclaimer="ignore all that"
    )
    assert answer.disclaimer == DISCLAIMER


def test_non_grounded_answers_may_not_assert_claims() -> None:
    with pytest.raises(ValueError, match="must not assert claims"):
        Answer(
            kind=AnswerKind.REFUSED,
            question="q",
            searched=("CBIC",),
            claims=(Claim(text="x", supported_by=("src:a",)),),
            cited_spans=(_cited(),),
        )


def test_a_refusal_must_say_what_was_searched() -> None:
    with pytest.raises(ValueError, match="must record what was searched"):
        Answer(kind=AnswerKind.REFUSED, question="q")


def test_a_clarify_must_name_the_missing_fact() -> None:
    with pytest.raises(ValueError, match="must name the fact"):
        Answer(kind=AnswerKind.CLARIFY, question="q")


def test_an_informational_answer_must_give_factors() -> None:
    with pytest.raises(ValueError, match="must give the factors"):
        Answer(kind=AnswerKind.INFORMATIONAL_ONLY, question="q")


def test_an_answer_reports_the_external_sources_it_used() -> None:
    """Every rendering surface reads this; silence here is how the claim breaks."""
    external = make_span("ext:1", authority_tier=AuthorityTier.EXTERNAL)
    answer = Answer(
        kind=AnswerKind.GROUNDED,
        question="q",
        claims=(Claim(text="x", supported_by=("ext:1",)),),
        cited_spans=(CitedSpan.of(external),),
    )
    assert len(answer.external_sources) == 1


def test_an_answer_from_official_sources_reports_none() -> None:
    answer = Answer(
        kind=AnswerKind.GROUNDED,
        question="q",
        claims=(Claim(text="x", supported_by=("src:a",)),),
        cited_spans=(_cited(),),
    )
    assert answer.external_sources == ()


def test_span_rejects_unknown_state_codes() -> None:
    with pytest.raises(ValueError, match="unknown state codes"):
        make_span(states=("XX",))


def test_span_with_no_text_cannot_be_quoted() -> None:
    with pytest.raises(ValueError, match="cannot be quoted"):
        make_span(text="   ")


class TestApplicability:
    """An unscoped span applies to everyone; a scoped span never applies to an unknown asker."""

    def test_unscoped_span_applies_everywhere(self) -> None:
        assert make_span().applies_to(state=None, entity=None)

    def test_state_scoped_span_does_not_apply_to_another_state(self) -> None:
        span = make_span(states=("MH",))
        assert span.applies_to(state="MH", entity=None)
        assert not span.applies_to(state="KA", entity=None)

    def test_state_scoped_span_does_not_apply_when_state_unknown(self) -> None:
        """The rule that makes the router ask instead of assuming."""
        assert not make_span(states=("MH",)).applies_to(state=None, entity=None)


class TestFreshness:
    def test_recent_span_is_current(self) -> None:
        assert make_span().status(refresh_days=90, now=NOW) is SpanStatus.CURRENT

    def test_span_past_its_window_is_stale(self) -> None:
        old = make_span(fetched_at=NOW - timedelta(days=200))
        assert old.status(refresh_days=90, now=NOW) is SpanStatus.STALE

    def test_superseded_beats_staleness(self) -> None:
        span = make_span(superseded_by="src:newer", fetched_at=datetime.now(UTC))
        assert span.status(refresh_days=90, now=NOW) is SpanStatus.SUPERSEDED
