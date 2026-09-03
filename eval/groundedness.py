"""Is the cited authority real, current, and applicable?

Structured cheapest-and-most-certain first, following the citation judge in the
hts-agent project. Reaching for a model judge immediately would be a mistake:
every failure below is decidable by structure alone, and a deterministic check
is both free and more trustworthy than an opinion.

The verdicts are ordered by how damaging they are:

* ``fabricated`` - the answer cites a span that was never retrieved. This is
  hallucinated law and the failure the whole project exists to prevent, so it
  carries **zero tolerance** in the gate: any occurrence fails the build. Note
  that the extractive answerer makes this structurally impossible; the check
  exists because it must still hold if a model-backed answerer is added, and a
  gate written only after the risk appears is a gate written too late.
* ``unofficial`` - the cited source is not on the allowlist. Also impossible by
  construction, also checked, for the same reason.
* ``superseded`` - a later instrument in the corpus replaced the cited one.
* ``out_of_scope`` - a state-specific or entity-specific span cited for a
  different state or entity. The subtlest of these: the citation is real, the
  text is apt, and the answer is still wrong for the person who asked.
* ``stale`` - past its refresh window. Nobody has confirmed it recently enough.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from agent.schema import Answer, SourceSpan, SpanStatus
from sources.loader import Allowlist, NotAllowlisted


class Verdict(StrEnum):
    SUPPORTS = "supports"
    FABRICATED = "fabricated"
    UNOFFICIAL = "unofficial"
    SUPERSEDED = "superseded"
    OUT_OF_SCOPE = "out_of_scope"
    STALE = "stale"


@dataclass(frozen=True)
class Check:
    span_id: str
    verdict: Verdict
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.SUPPORTS


@dataclass
class GroundednessReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.checks)

    def rate(self, verdict: Verdict) -> float:
        return sum(c.verdict is verdict for c in self.checks) / self.n if self.n else 0.0

    @property
    def faithful_rate(self) -> float:
        return self.rate(Verdict.SUPPORTS)

    @property
    def fabricated_rate(self) -> float:
        """Must be zero. This is a bug, not a score."""
        return self.rate(Verdict.FABRICATED)

    @property
    def unofficial_rate(self) -> float:
        return self.rate(Verdict.UNOFFICIAL)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for check in self.checks:
            out[check.verdict.value] = out.get(check.verdict.value, 0) + 1
        return out

    def __str__(self) -> str:
        return (
            f"citations={self.n} faithful={self.faithful_rate:.3f} "
            f"fabricated={self.fabricated_rate:.3f} unofficial={self.unofficial_rate:.3f} "
            f"{self.counts()}"
        )


def check_answer(
    answer: Answer,
    *,
    retrieved: Sequence[SourceSpan],
    allowlist: Allowlist,
) -> list[Check]:
    """Structural checks for one answer."""
    retrieved_ids = {s.span_id for s in retrieved}
    by_id = {s.span_id: s for s in retrieved}
    checks: list[Check] = []

    for cited in answer.cited_spans:
        if cited.span_id not in retrieved_ids:
            checks.append(
                Check(
                    cited.span_id,
                    Verdict.FABRICATED,
                    "cited authority was never retrieved - the system was not shown this text",
                )
            )
            continue

        try:
            allowlist.get(cited.span_id.split(":")[0])
        except NotAllowlisted:
            checks.append(
                Check(cited.span_id, Verdict.UNOFFICIAL, "source is not on the allowlist")
            )
            continue

        if cited.status is SpanStatus.SUPERSEDED:
            checks.append(
                Check(cited.span_id, Verdict.SUPERSEDED, "replaced by a later instrument")
            )
            continue
        if cited.status is SpanStatus.STALE:
            checks.append(Check(cited.span_id, Verdict.STALE, "past its refresh window"))
            continue

        span = by_id[cited.span_id]
        if not span.applies_to(state=answer.applies_to.state, entity=answer.applies_to.entity_type):
            checks.append(
                Check(
                    cited.span_id,
                    Verdict.OUT_OF_SCOPE,
                    f"span scope {span.states or 'all-India'}/{span.entity_types or 'any entity'} "
                    f"does not cover {answer.applies_to.describe()}",
                )
            )
            continue

        checks.append(Check(cited.span_id, Verdict.SUPPORTS))
    return checks
