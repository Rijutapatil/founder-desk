"""Run the evaluation and report."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from agent.answerer import Answerer, build_answerer
from agent.retrieval.embedder import load_embedder
from agent.retrieval.rerank import Reranker, load_reranker
from agent.router import route
from agent.schema import AnswerKind
from eval.dataset import Example, load_examples
from eval.metrics import RetrievalMetrics, RoutingMetrics


@dataclass
class EvalReport:
    system: str
    retrieval: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    routing: RoutingMetrics = field(default_factory=RoutingMetrics)
    cost_usd: float = 0.0
    misses: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.routing.n

    def summary(self) -> str:
        lines = [
            f"system: {self.system}   n={self.n}   cost=${self.cost_usd:.4f}",
            "",
            "retrieval (grounded questions only)",
            f"  recall@1  {self.retrieval.recall_at(1):.3f}",
            f"  recall@3  {self.retrieval.recall_at(3):.3f}",
            f"  recall@5  {self.retrieval.recall_at(5):.3f}",
            f"  recall@10 {self.retrieval.recall_at(10):.3f}",
            f"  MRR       {self.retrieval.mrr:.3f}",
            "",
            "routing",
            f"  overall accuracy   {self.routing.accuracy:.3f}",
        ]
        for kind in AnswerKind:
            total = sum(v for (e, _), v in self.routing.matrix.items() if e is kind)
            if total:
                lines.append(
                    f"  {kind.value:<18} {self.routing.accuracy_for(kind):.3f}  (n={total})"
                )
        lines.append(
            f"  over-refusal       {self.routing.over_refusal:.3f}  (answerable questions refused)"
        )
        if self.routing.confusions():
            lines += ["", "confusions"] + [f"  {c}" for c in self.routing.confusions()]
        return "\n".join(lines)


def evaluate(answerer: Answerer, examples: list[Example], *, system: str) -> EvalReport:
    report = EvalReport(system=system)
    for example in examples:
        answer = answerer.answer(example.question)
        report.routing.record(example.expected_kind, answer.kind)

        if example.gold_span:
            # Retrieval is scored on the wide candidate set, before the coverage
            # gate, so a recall number never silently reflects a routing choice.
            ranked = [
                h.span.span_id for h in answerer.retrieve(example.question, route(example.question))
            ]
            wide = [h.span.span_id for h in answerer.store.search(example.question, k=10)]
            merged = ranked + [s for s in wide if s not in ranked]
            report.retrieval.record(example.gold_span, merged)
            if example.gold_span not in merged[:5]:
                report.misses.append(f"{example.question[:66]} -> want {example.gold_span}")
    return report


def sweep_coverage(examples: list[Example], reranker: Reranker | None = None) -> str:
    """Choose the refusal threshold from data rather than by eye.

    Prints routing accuracy across candidate thresholds. The trade is explicit:
    a low threshold answers almost everything (and answers off-topic questions
    with a confident irrelevant citation), a high one refuses questions the
    corpus can genuinely answer.
    """
    rows = ["threshold  overall  grounded  refused  over-refusal"]
    for threshold in [round(0.02 * i, 2) for i in range(5, 26)]:
        answerer = build_answerer(reranker)
        answerer.min_coverage = threshold
        report = evaluate(answerer, examples, system=f"coverage={threshold}")
        rows.append(
            f"    {threshold:.2f}    {report.routing.accuracy:.3f}     "
            f"{report.routing.accuracy_for(AnswerKind.GROUNDED):.3f}    "
            f"{report.routing.accuracy_for(AnswerKind.REFUSED):.3f}         "
            f"{report.routing.over_refusal:.3f}"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reranker", default="auto", choices=("auto", "identity", "cross-encoder"))
    parser.add_argument("--embedder", default="auto", choices=("auto", "hashing", "model"))
    parser.add_argument(
        "--compare-embedder", action="store_true", help="hashing vs model, reranker held fixed"
    )
    parser.add_argument("--compare-rerank", action="store_true", help="identity vs cross-encoder")
    parser.add_argument("--sweep", action="store_true", help="sweep the refusal threshold")
    parser.add_argument("--misses", action="store_true", help="list retrieval misses")
    args = parser.parse_args()

    examples = load_examples()

    if args.sweep:
        print(sweep_coverage(examples))
        return 0

    if args.compare_rerank:
        for name in ("identity", "cross-encoder"):
            try:
                answerer = build_answerer(load_reranker(name))
            except ImportError as exc:
                print(f"\n{name}: unavailable - {exc}")
                continue
            report = evaluate(answerer, examples, system=name)
            print("\n" + "=" * 62)
            print(report.summary())
        return 0

    if args.compare_embedder:
        for name in ("hashing", "model"):
            answerer = build_answerer(load_reranker(args.reranker), load_embedder(name))
            report = evaluate(answerer, examples, system=f"{name} + {args.reranker}")
            print("\n" + "=" * 62)
            print(report.summary())
        return 0

    reranker = load_reranker(args.reranker)
    answerer = build_answerer(reranker, load_embedder(args.embedder))
    gate = "relevance" if reranker.name.startswith("cross-encoder") else "coverage"
    report = evaluate(answerer, examples, system=f"{reranker.name} gate={gate}")
    print(report.summary())
    if args.misses and report.misses:
        print("\nretrieval misses (gold not in top 5)")
        for miss in report.misses:
            print(f"  {miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
