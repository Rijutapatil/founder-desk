"""CI quality gate: fail the build when quality regresses.

The point is not to enforce a fixed accuracy - that would block legitimate
work-in-progress - but to make a *regression* impossible to merge without
someone noticing. The baseline is committed to the repo, so "did this get
worse" is answerable in review rather than only on the author's laptop.

Different metrics get different tolerances, because they mean different things:

* **Retrieval and routing** - a small absolute tolerance. Some run-to-run
  variation is legitimate as the corpus is re-fetched.
* **Fabricated and unofficial citations** - zero tolerance. A system citing
  authority it was never shown, or a source outside the allowlist, is broken
  rather than merely worse.
* **Over-refusal** - gated upward, because the cheapest way to make every other
  number look good is to refuse more. Without this, a change that quietly turns
  the system into "I cannot answer that" passes every other check.
* **Citation faithfulness** - gated downward. Fabrication is the loud failure,
  but the quiet one is a corpus rotting in place: sources drift past their
  refresh windows, every citation becomes ``stale``, and the retrieval and
  routing numbers do not move at all because retrieval is still finding exactly
  the right span. Only faithfulness registers it. Verified by backdating the
  corpus: faithfulness fell 1.000 -> 0.753 while every other metric held.
* **Cost** - a wide tolerance, but gated: buying a point of accuracy for triple
  the spend should be a decision someone makes on purpose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.schema import AnswerKind

DEFAULT_BASELINE = Path(__file__).resolve().parent / "baseline_metrics.json"

ACCURACY_TOLERANCE = 0.02
OVER_REFUSAL_TOLERANCE = 0.05
COST_TOLERANCE_RATIO = 0.25
ZERO_TOLERANCE = 0.0


@dataclass
class GateFailure:
    metric: str
    baseline: float
    current: float
    tolerance: float

    def __str__(self) -> str:
        return (
            f"{self.metric}: {self.current:.4f} vs baseline {self.baseline:.4f} "
            f"(tolerance {self.tolerance:.4f})"
        )


@dataclass
class GateResult:
    failures: list[GateFailure] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def __str__(self) -> str:
        lines = ["PASS" if self.passed else "FAIL"]
        lines += [f"  regression: {f}" for f in self.failures]
        lines += [f"  improved:   {i}" for i in self.improvements]
        lines += [f"  note:       {n}" for n in self.notes]
        return "\n".join(lines)


def snapshot(report: Any, grounding: Any, *, system: str) -> dict[str, Any]:
    """Reduce a run to the numbers the gate tracks."""
    return {
        "system": system,
        "n": report.n,
        "cost_per_answer": report.cost_usd / report.n if report.n else 0.0,
        "retrieval": {
            "recall@1": report.retrieval.recall_at(1),
            "recall@5": report.retrieval.recall_at(5),
            "mrr": report.retrieval.mrr,
        },
        "routing": {
            "overall": report.routing.accuracy,
            "over_refusal": report.routing.over_refusal,
            "refused": report.routing.accuracy_for(AnswerKind.REFUSED),
        },
        "grounding": {
            "faithful": grounding.faithful_rate,
            "fabricated": grounding.fabricated_rate,
            "unofficial": grounding.unofficial_rate,
            "n_citations": grounding.n,
        },
    }


def _worse(current: float, base: float, tol: float) -> bool:
    return current < base - tol


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> GateResult:
    result = GateResult()

    if baseline.get("n") and current.get("n") != baseline.get("n"):
        result.notes.append(
            f"question count changed ({baseline['n']} -> {current['n']}); "
            "comparison is not strictly like-for-like"
        )

    for group, key in (
        ("retrieval", "recall@1"),
        ("retrieval", "recall@5"),
        ("retrieval", "mrr"),
        ("routing", "overall"),
        ("routing", "refused"),
        ("grounding", "faithful"),
    ):
        base = baseline.get(group, {}).get(key)
        cur = current.get(group, {}).get(key)
        if base is None or cur is None:
            result.notes.append(f"{group}.{key} missing from a run")
            continue
        if _worse(cur, base, ACCURACY_TOLERANCE):
            result.failures.append(GateFailure(f"{group}.{key}", base, cur, ACCURACY_TOLERANCE))
        elif cur > base + ACCURACY_TOLERANCE:
            result.improvements.append(f"{group}.{key}: {base:.4f} -> {cur:.4f}")

    # Over-refusal is the one metric where *higher is worse*.
    base_or = baseline.get("routing", {}).get("over_refusal", 0.0)
    cur_or = current.get("routing", {}).get("over_refusal", 0.0)
    if cur_or > base_or + OVER_REFUSAL_TOLERANCE:
        result.failures.append(
            GateFailure("routing.over_refusal", base_or, cur_or, OVER_REFUSAL_TOLERANCE)
        )

    for key in ("fabricated", "unofficial"):
        base = baseline.get("grounding", {}).get(key, 0.0)
        cur = current.get("grounding", {}).get(key, 0.0)
        if cur > base + ZERO_TOLERANCE:
            result.failures.append(GateFailure(f"grounding.{key}", base, cur, ZERO_TOLERANCE))

    base_cost = baseline.get("cost_per_answer", 0.0)
    cur_cost = current.get("cost_per_answer", 0.0)
    if base_cost > 0 and cur_cost > base_cost * (1 + COST_TOLERANCE_RATIO):
        result.failures.append(
            GateFailure("cost_per_answer", base_cost, cur_cost, COST_TOLERANCE_RATIO)
        )
    return result


def load_baseline(path: Path = DEFAULT_BASELINE) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def write_baseline(current: dict[str, Any], path: Path = DEFAULT_BASELINE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2) + "\n")
