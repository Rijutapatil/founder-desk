"""What is measured, and why each number is here.

Four metrics, because a single accuracy figure would hide the failure that
matters most in this domain.

* **Retrieval recall@k** - is the right span in the candidate set at all? This
  is the ceiling on everything downstream: no reranker and no model can cite a
  span retrieval never returned.
* **MRR** - where in the list it lands. Recall@5 can hold steady while quality
  quietly degrades from rank 1 to rank 5, and MRR catches that.
* **Routing accuracy** - did the system pick the right *kind* of response? A
  system that answers a state-dependent question all-India, or recommends a
  company structure, has failed even when its citation is real.
* **Refusal correctness, reported separately from the rest.** It is the metric
  most easily gamed in both directions: refuse everything and routing accuracy
  on the refusal slice hits 1.00 while the system becomes useless. So refusal
  rate on answerable questions is reported alongside it, and the two must be
  read together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from agent.schema import AnswerKind


@dataclass
class RetrievalMetrics:
    n: int = 0
    hits_at: dict[int, int] = field(default_factory=dict)
    reciprocal_ranks: list[float] = field(default_factory=list)

    def record(self, gold: str, ranked: Sequence[str], ks: Sequence[int] = (1, 3, 5, 10)) -> None:
        self.n += 1
        rank = next((i + 1 for i, span_id in enumerate(ranked) if span_id == gold), None)
        self.reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        for k in ks:
            if rank is not None and rank <= k:
                self.hits_at[k] = self.hits_at.get(k, 0) + 1

    def recall_at(self, k: int) -> float:
        return self.hits_at.get(k, 0) / self.n if self.n else 0.0

    @property
    def mrr(self) -> float:
        return (
            sum(self.reciprocal_ranks) / len(self.reciprocal_ranks)
            if self.reciprocal_ranks
            else 0.0
        )


@dataclass
class RoutingMetrics:
    """Confusion between expected and actual answer kinds."""

    matrix: dict[tuple[AnswerKind, AnswerKind], int] = field(default_factory=dict)

    def record(self, expected: AnswerKind, actual: AnswerKind) -> None:
        key = (expected, actual)
        self.matrix[key] = self.matrix.get(key, 0) + 1

    @property
    def n(self) -> int:
        return sum(self.matrix.values())

    @property
    def accuracy(self) -> float:
        correct = sum(v for (e, a), v in self.matrix.items() if e == a)
        return correct / self.n if self.n else 0.0

    def accuracy_for(self, expected: AnswerKind) -> float:
        total = sum(v for (e, _), v in self.matrix.items() if e == expected)
        correct = sum(v for (e, a), v in self.matrix.items() if e == expected and a == expected)
        return correct / total if total else 0.0

    @property
    def over_refusal(self) -> float:
        """Share of answerable questions that were refused.

        The counterweight to refusal accuracy. Without it, a system could score
        perfectly on refusals by refusing everything.
        """
        answerable = sum(v for (e, _), v in self.matrix.items() if e is AnswerKind.GROUNDED)
        refused = sum(
            v
            for (e, a), v in self.matrix.items()
            if e is AnswerKind.GROUNDED and a is AnswerKind.REFUSED
        )
        return refused / answerable if answerable else 0.0

    def confusions(self) -> list[str]:
        return [
            f"{e.value} -> {a.value}: {v}"
            for (e, a), v in sorted(self.matrix.items(), key=lambda kv: -kv[1])
            if e != a
        ]
