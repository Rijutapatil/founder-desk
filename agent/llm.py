"""Model interface.

Deliberately thin, and deliberately optional. The default answering path in this
project is **extractive**: it quotes the retrieved span rather than writing prose
about it, so there is no generation step that could hallucinate and no API key
required to get a real answer.

A model becomes useful for one job - synthesising several spans into connected
prose - and that job is strictly additive. It is gated behind this protocol so
that every measured number in the evaluation stays reproducible without network
access or spend, and so a missing key degrades the system to "quotes the source"
rather than to "does not work".

``ScriptedModel`` is what the tests use: deterministic, offline, and unable to
fabricate, since it can only return what it was handed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage = Usage()


class StructuredModel(Protocol):
    """Synthesises prose from spans it was given. It is never a source of facts."""

    @property
    def name(self) -> str: ...

    def synthesise(self, question: str, passages: Sequence[str]) -> Completion: ...


class ScriptedModel:
    """Offline stand-in: concatenates the passages it was given, nothing more.

    Useful precisely because it cannot introduce a claim that was not retrieved,
    which makes it a clean control when testing the groundedness judge.
    """

    def __init__(self, name: str = "scripted") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def synthesise(self, question: str, passages: Sequence[str]) -> Completion:
        return Completion(text=" ".join(passages), usage=Usage())
