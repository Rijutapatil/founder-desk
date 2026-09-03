"""CI entry point for the quality gate.

Runs the zero-cost retrieval baseline, compares it to the committed baseline
metrics, and exits non-zero on regression.

Only the model-free system is gated per-commit, deliberately: it needs no API
key, no billing and no network, so *every* pull request is checked rather than
only the ones where someone remembers to run an eval.

Usage::

    python -m eval.gate_cli
    python -m eval.gate_cli --update    # accept the current run as the baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.router import route
from eval.baselines.retrieval import nearest_faq_baseline
from eval.dataset import load_examples
from eval.gate import DEFAULT_BASELINE, compare_to_baseline, load_baseline, snapshot, write_baseline
from eval.groundedness import GroundednessReport, check_answer
from eval.runner import evaluate
from ingest.build_corpus import load_spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    if not load_spans():
        # A fresh clone with no built corpus. Skipping is correct: failing here
        # would make the gate a barrier to contribution rather than to regression.
        print("no corpus on disk; skipping quality gate (run python -m ingest.build_corpus)")
        return 0

    examples = load_examples()
    answerer = nearest_faq_baseline()
    report = evaluate(answerer, examples, system="nearest-faq")

    grounding = GroundednessReport()
    for example in examples:
        answer = answerer.answer(example.question)
        if not answer.cited_spans:
            continue
        retrieved = [h.span for h in answerer.retrieve(example.question, route(example.question))]
        grounding.checks.extend(
            check_answer(answer, retrieved=retrieved, allowlist=answerer.allowlist)
        )

    current = snapshot(report, grounding, system="nearest-faq")

    if args.update:
        write_baseline(current, args.baseline)
        print(f"baseline updated -> {args.baseline}")
        return 0

    previous = load_baseline(args.baseline)
    if previous is None:
        write_baseline(current, args.baseline)
        print(f"no baseline found; wrote initial baseline -> {args.baseline}")
        return 0

    gate = compare_to_baseline(current, previous)
    print(gate)
    print()
    print(report.summary())
    print()
    print(f"grounding: {grounding}")
    return 0 if gate.passed else 1


if __name__ == "__main__":
    sys.exit(main())
