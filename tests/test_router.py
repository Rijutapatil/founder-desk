"""Routing: extract the deciding facts, and never invent one."""

from __future__ import annotations

import pytest

from agent.router import detect_entity, detect_state, detect_turnover, route
from agent.schema import EntityType


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("do I need to register in Karnataka", "KA"),
        ("my office is in West Bengal", "WB"),
        ("registered in Andhra Pradesh", "AP"),
        ("do I need GST registration", None),
    ],
)
def test_state_detection(question: str, expected: str | None) -> None:
    assert detect_state(question) == expected


def test_a_city_never_implies_a_state() -> None:
    """A registered office can sit in a different state from the operation.

    This is the single most tempting inference in the whole system and the most
    dangerous, so it is pinned: mentioning Mumbai must produce a question, not
    an assumption of Maharashtra.
    """
    routing = route("do I need shops and establishment registration in Mumbai")
    assert routing.applicability.state is None
    assert routing.missing_state
    assert "mumbai" in routing.mentioned_cities
    assert "Mumbai" in routing.clarifying_question()


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("as an LLP do I file returns", EntityType.LLP),
        ("my one person company", EntityType.OPC),
        ("we are a private limited company", EntityType.PVT_LTD),
        ("I run a sole proprietorship", EntityType.SOLE_PROP),
        ("what is the GST threshold", None),
    ],
)
def test_entity_detection(question: str, expected: EntityType | None) -> None:
    assert detect_entity(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("my turnover is 45 lakh", "45 lakh"),
        ("we did 2 crore last year", "2 crore"),
        ("how much tax do I pay", None),
    ],
)
def test_turnover_detection(question: str, expected: str | None) -> None:
    assert detect_turnover(question) == expected


def test_explicit_arguments_beat_inference() -> None:
    routing = route("do I need to register in Karnataka", state="MH")
    assert routing.applicability.state == "MH"


@pytest.mark.parametrize(
    "question",
    [
        "do I need shops and establishment registration",
        "is professional tax applicable to us",
        "what is the stamp duty on a rent agreement",
    ],
)
def test_state_dependent_topics_are_flagged(question: str) -> None:
    assert route(question).missing_state


def test_state_dependent_question_with_a_state_is_not_blocked() -> None:
    assert not route("professional tax in Karnataka").missing_state


@pytest.mark.parametrize(
    "question",
    [
        "should I register an LLP or a Pvt Ltd",
        "which is better for a startup, OPC or private limited",
        "is it worth registering for GST voluntarily",
        "what would you recommend for my structure",
    ],
)
def test_requests_for_a_recommendation_are_flagged(question: str) -> None:
    assert route(question).is_judgement


def test_a_judgement_question_does_not_adopt_a_mentioned_entity() -> None:
    """ "Should I register an LLP or a Pvt Ltd" mentions an LLP without being about one."""
    routing = route("should I register an LLP or a Pvt Ltd")
    assert routing.is_judgement
    assert routing.applicability.entity_type is None


def test_an_explicit_entity_survives_a_judgement_question() -> None:
    from agent.schema import EntityType as E

    routing = route("should I opt for the composition scheme", entity=E.PVT_LTD)
    assert routing.applicability.entity_type is E.PVT_LTD


def test_a_factual_question_is_not_a_judgement_question() -> None:
    assert not route("what is the GST registration threshold").is_judgement
