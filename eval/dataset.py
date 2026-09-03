"""Load the evaluation set."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from agent.schema import AnswerKind, SourceSpan

QUESTIONS_PATH = Path(__file__).parent / "questions.yaml"

_KIND_BY_SECTION = {
    "grounded": AnswerKind.GROUNDED,
    "refused": AnswerKind.REFUSED,
    "clarify": AnswerKind.CLARIFY,
    "informational": AnswerKind.INFORMATIONAL_ONLY,
}


@dataclass(frozen=True)
class Example:
    question: str
    expected_kind: AnswerKind
    source: str | None = None
    anchor: str | None = None
    gold_span: str | None = None

    @property
    def domain_label(self) -> str:
        return self.source or "-"


class UnresolvedGold(ValueError):
    """A gold label no longer matches exactly one span."""


def resolve_gold(examples: list[Example], spans: Sequence[SourceSpan]) -> list[Example]:
    """Bind each gold label to a span id by matching its anchor phrase.

    Labels reference a *phrase from the source question*, never a span id. Span
    ids are content hashes and would look stable enough to hardcode, but pinning
    them in the eval file would mean any upstream wording change turns a label
    into a dangling reference that silently scores zero and reads as a retrieval
    regression. An anchor fails loudly instead, and says which label broke.

    Ambiguity is an error too: an anchor matching two spans would make the
    "correct" answer arbitrary.
    """
    resolved: list[Example] = []
    for example in examples:
        if not example.anchor:
            resolved.append(example)
            continue
        needle = example.anchor.lower()
        matches = [s for s in spans if s.source_id == example.source and needle in s.text.lower()]
        if len(matches) != 1:
            raise UnresolvedGold(
                f"anchor {example.anchor!r} in {example.source} matched {len(matches)} spans "
                f"(expected exactly 1) for question: {example.question!r}"
            )
        resolved.append(replace(example, gold_span=matches[0].span_id))
    return resolved


def load_examples(
    path: Path = QUESTIONS_PATH, *, spans: Sequence[SourceSpan] | None = None
) -> list[Example]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    examples: list[Example] = []
    for section, kind in _KIND_BY_SECTION.items():
        for item in raw.get(section) or []:
            examples.append(
                Example(
                    question=item["q"],
                    expected_kind=kind,
                    source=item.get("source"),
                    anchor=item.get("anchor"),
                )
            )
    if not examples:
        raise ValueError(f"{path} contains no examples")

    if spans is None:
        from ingest.build_corpus import load_spans

        spans = load_spans()
    return resolve_gold(examples, spans) if spans else examples
