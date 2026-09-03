"""The citation judge - structural checks that need no model."""

from __future__ import annotations

from datetime import timedelta

from agent.schema import Answer, AnswerKind, Applicability, CitedSpan, Claim, SpanStatus
from eval.groundedness import GroundednessReport, Verdict, check_answer
from tests.conftest import NOW, make_span


def _answer(cited: list[CitedSpan], **kw) -> Answer:
    return Answer(
        kind=AnswerKind.GROUNDED,
        question="q",
        claims=tuple(Claim(text="x", supported_by=(c.span_id,)) for c in cited),
        cited_spans=tuple(cited),
        **kw,
    )


def test_a_span_that_was_never_retrieved_is_fabricated(allowlist) -> None:
    ghost = make_span("src:ghost")
    checks = check_answer(_answer([CitedSpan.of(ghost)]), retrieved=[], allowlist=allowlist)
    assert checks[0].verdict is Verdict.FABRICATED


def test_a_source_outside_the_allowlist_is_unofficial(allowlist) -> None:
    rogue = make_span("blogspam:1")
    checks = check_answer(_answer([CitedSpan.of(rogue)]), retrieved=[rogue], allowlist=allowlist)
    assert checks[0].verdict is Verdict.UNOFFICIAL


def test_a_stale_citation_is_flagged(allowlist) -> None:
    old = make_span(fetched_at=NOW - timedelta(days=400))
    checks = check_answer(
        _answer([CitedSpan.of(old, status=SpanStatus.STALE)]), retrieved=[old], allowlist=allowlist
    )
    assert checks[0].verdict is Verdict.STALE


def test_a_superseded_citation_is_flagged(allowlist) -> None:
    span = make_span(superseded_by="src:newer")
    checks = check_answer(
        _answer([CitedSpan.of(span, status=SpanStatus.SUPERSEDED)]),
        retrieved=[span],
        allowlist=allowlist,
    )
    assert checks[0].verdict is Verdict.SUPERSEDED


def test_a_maharashtra_rule_cited_for_karnataka_is_out_of_scope(allowlist) -> None:
    """The subtle one: the citation is real, the text is apt, the answer is wrong."""
    span = make_span(states=("MH",))
    checks = check_answer(
        _answer([CitedSpan.of(span)], applies_to=Applicability(state="KA")),
        retrieved=[span],
        allowlist=allowlist,
    )
    assert checks[0].verdict is Verdict.OUT_OF_SCOPE


def test_a_good_citation_supports(allowlist) -> None:
    span = make_span()
    checks = check_answer(_answer([CitedSpan.of(span)]), retrieved=[span], allowlist=allowlist)
    assert checks[0].verdict is Verdict.SUPPORTS
    assert checks[0].ok


def test_report_rates() -> None:
    from eval.groundedness import Check

    report = GroundednessReport(
        checks=[
            Check("a", Verdict.SUPPORTS),
            Check("b", Verdict.FABRICATED),
            Check("c", Verdict.SUPPORTS),
            Check("d", Verdict.STALE),
        ]
    )
    assert report.faithful_rate == 0.5
    assert report.fabricated_rate == 0.25
    assert report.counts()["stale"] == 1
