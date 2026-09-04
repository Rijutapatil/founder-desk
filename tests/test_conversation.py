"""Multi-turn sessions.

The behaviour under test is the one a single-shot interface cannot have: a
clarifying question that can actually be answered.
"""

from __future__ import annotations

import pytest

from agent.answerer import build_answerer
from agent.conversation import Conversation, resolve_state_reply
from agent.schema import AnswerKind, EntityType
from ingest.build_corpus import load_spans

pytestmark = pytest.mark.skipif(not load_spans(), reason="no corpus on disk")


@pytest.fixture(scope="module")
def answerer():
    return build_answerer()


class TestStateReply:
    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ("Maharashtra", "MH"),
            ("maharashtra", "MH"),
            ("MH", "MH"),
            ("Karnataka.", "KA"),
            ("we are in Tamil Nadu", "TN"),
            ("our registered office is in Gujarat", "GJ"),
        ],
    )
    def test_short_replies_read_as_states(self, reply: str, expected: str) -> None:
        assert resolve_state_reply(reply) == expected

    @pytest.mark.parametrize(
        "message",
        [
            "what is the GST registration threshold for services",
            # The one that matters: it names a state and is still a new
            # question. Treating it as a reply would answer the *previous*
            # question and show a jurisdiction nobody asked about.
            "do I need PF registration in Karnataka",
        ],
    )
    def test_a_new_question_is_not_read_as_a_state_answer(self, message: str) -> None:
        assert resolve_state_reply(message) is None

    def test_an_unrecognised_short_reply_is_not_a_state(self) -> None:
        assert resolve_state_reply("yes please") is None


class TestSession:
    def test_a_clarifying_question_can_be_answered_by_the_next_message(self, answerer) -> None:
        c = Conversation(answerer)
        first = c.ask("do I need shops and establishment registration")
        assert first.answer.kind is AnswerKind.CLARIFY

        second = c.ask("Maharashtra")
        assert second.resolved_from_pending
        assert second.question == "do I need shops and establishment registration"
        assert c.state == "MH"
        assert second.answer.kind is not AnswerKind.CLARIFY

    def test_facts_carry_forward(self, answerer) -> None:
        c = Conversation(answerer)
        c.ask("we are an LLP in Karnataka - do we need GST registration")
        assert c.state == "KA"
        assert c.entity is EntityType.LLP
        assert "state: KA" in c.known

        later = c.ask("what about provident fund")
        assert later.answer.applies_to.state == "KA"

    def test_reset_forgets_everything(self, answerer) -> None:
        c = Conversation(answerer)
        c.ask("do I need GST registration in Maharashtra")
        assert c.state == "MH"
        c.reset()
        assert c.state is None
        assert c.known == "nothing established yet"

    def test_a_pending_question_is_dropped_once_answered(self, answerer) -> None:
        c = Conversation(answerer)
        c.ask("do I need shops and establishment registration")
        c.ask("Maharashtra")
        assert c._pending is None

    def test_an_unrelated_message_does_not_resolve_the_pending_question(self, answerer) -> None:
        """A follow-up that is not a state must be treated as its own question."""
        c = Conversation(answerer)
        c.ask("do I need shops and establishment registration")
        turn = c.ask("can a one person company get startup india benefits")
        assert not turn.resolved_from_pending
        assert turn.question == "can a one person company get startup india benefits"

    def test_turns_are_recorded(self, answerer) -> None:
        c = Conversation(answerer)
        c.ask("can a one person company get startup india benefits")
        c.ask("does an apprentice have to be enrolled in provident fund")
        assert len(c.turns) == 2
