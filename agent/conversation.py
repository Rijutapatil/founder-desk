"""Multi-turn sessions.

The single-shot interface has an obvious dead end. A state-dependent question
returns "which state is the registered office in?" — and then there is nowhere to
put the answer. The founder has to retype the whole question with `--state MH`,
which is the opposite of what a clarifying question is for.

A conversation fixes that with two ideas and no model:

**A pending question.** When a turn ends in `clarify`, the question is held. The
next turn is first tried as an *answer to that question* — "Maharashtra", "MH",
"we're in Karnataka" — and if it resolves the missing fact, the held question is
re-asked with it and answered.

**Remembered facts.** Once the state or entity type is known it carries forward,
so the second and third questions do not have to repeat it. Facts are only ever
learned from what the founder actually said: a remembered state comes from an
explicit statement, never from an inference the router refused to make.

Everything else is unchanged — same extractive answering, same grounding
contract, same refusals. This is a session around the engine, not a new engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.answerer import Answerer
from agent.router import STATE_NAMES, detect_entity, detect_state
from agent.schema import INDIAN_STATES, Answer, AnswerKind, EntityType

# Filler a person puts around a bare answer. Anything left over after removing
# the state and these means the message is a new question, not a reply.
_FILLER = frozenset(
    """we are is in it the of our my a an and i im i'm us at based state
    registered office located sits sitting company firm business here yes it's""".split()
)
_WORD = re.compile(r"[a-z']+")


def resolve_state_reply(message: str) -> str | None:
    """Read a message as an answer to "which state?", or return None.

    The test is not length, it is *remainder*: strip the state the message names
    and the filler around it, and if anything substantive is left, this is a new
    question that happens to mention a state rather than a reply to the pending
    one. "we are in Tamil Nadu" resolves; "do I need PF registration in
    Karnataka" does not, and is answered as its own question with Karnataka
    applied.

    Getting this wrong in the permissive direction is the failure that matters:
    it would silently answer the *previous* question and show the founder a
    jurisdiction they did not ask about.
    """
    code = detect_state(message)
    if code is None:
        token = message.strip().strip(".,!? ").upper()
        return token if token in INDIAN_STATES and len(token) == 2 else None

    name = next((n for n, c in STATE_NAMES.items() if c == code and n in message.lower()), None)
    remainder = message.lower().replace(name, " ") if name else message.lower()
    leftover = [w for w in _WORD.findall(remainder) if w not in _FILLER]
    return code if not leftover else None


@dataclass
class Turn:
    question: str
    answer: Answer
    resolved_from_pending: bool = False


@dataclass
class Conversation:
    """A session over one :class:`Answerer`."""

    answerer: Answerer
    state: str | None = None
    entity: EntityType | None = None
    turns: list[Turn] = field(default_factory=list)
    _pending: str | None = None

    @property
    def known(self) -> str:
        parts = []
        if self.entity:
            parts.append(f"entity: {self.entity.value}")
        if self.state:
            parts.append(f"state: {self.state}")
        return " · ".join(parts) if parts else "nothing established yet"

    def reset(self) -> None:
        self.state = None
        self.entity = None
        self._pending = None

    def ask(self, message: str) -> Turn:
        message = message.strip()

        # A held clarifying question gets first refusal on this message.
        resolved = False
        if self._pending:
            answered_state = resolve_state_reply(message)
            if answered_state:
                self.state = answered_state
                message, self._pending = self._pending, None
                resolved = True

        # Learn facts the founder stated, but never infer them - detect_state and
        # detect_entity both return None rather than guessing, and that is the
        # property being preserved across turns.
        if (stated := detect_state(message)) is not None:
            self.state = stated
        if (stated_entity := detect_entity(message)) is not None:
            self.entity = stated_entity

        answer = self.answerer.answer(message, state=self.state, entity=self.entity)

        # Hold an unanswered clarification so the next message can resolve it.
        self._pending = message if answer.kind is AnswerKind.CLARIFY else None

        turn = Turn(question=message, answer=answer, resolved_from_pending=resolved)
        self.turns.append(turn)
        return turn
