"""CI entry point for the quality gate.

Compares a fresh run to a committed baseline and exits non-zero on regression.

Two systems are gated, against two committed baselines, because the project ships
two refusal gates:

* ``--reranker identity`` is the model-free path: no key, no billing, no
  network, no torch. It runs on **every pull request**, because a gate that is
  expensive is a gate that eventually gets disabled.
* ``--reranker cross-encoder`` is what actually ships when the reranking extra
  is installed, and it is a materially different system - refusal accuracy 0.654
  against 0.385. It is gated too, on pushes to main rather than per-PR, because
  it needs a 2 GB dependency and a model download.

Gating only the cheap one would mean the numbers in the README describe a system
CI never checks. Gating only the real one would mean contributors cannot run the
gate. So both, at different frequencies.

Usage::

    python -m eval.gate_cli
    python -m eval.gate_cli --reranker cross-encoder
    python -m eval.gate_cli --update    # accept the current run as the baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.answerer import build_answerer
from agent.retrieval.embedder import HashingEmbedder, SentenceTransformerEmbedder
from agent.retrieval.rerank import CrossEncoderReranker, IdentityReranker
from agent.router import route
from eval.dataset import load_examples
from eval.gate import DEFAULT_BASELINE, compare_to_baseline, load_baseline, snapshot, write_baseline
from eval.groundedness import GroundednessReport, check_answer
from eval.runner import evaluate
from ingest.build_corpus import load_spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reranker", default="identity", choices=("identity", "cross-encoder"))
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    baseline_path = args.baseline or (
        DEFAULT_BASELINE
        if args.reranker == "identity"
        else DEFAULT_BASELINE.with_name("baseline_metrics_reranked.json")
    )

    if not load_spans():
        # A fresh clone with no built corpus. Skipping is correct: failing here
        # would make the gate a barrier to contribution rather than to regression.
        print("no corpus on disk; skipping quality gate (run python -m ingest.build_corpus)")
        return 0

    examples = load_examples()
    # The two systems are pinned end to end, embedder included. Letting the
    # free gate pick "best available" would measure a torch-backed system on a
    # laptop and a hashing one in CI, under the same baseline file - so a real
    # regression could hide behind the difference between the two machines.
    try:
        if args.reranker == "identity":
            answerer = build_answerer(IdentityReranker(), HashingEmbedder())
        else:
            answerer = build_answerer(CrossEncoderReranker(), SentenceTransformerEmbedder())
    except ImportError as exc:
        print(f"cannot run the {args.reranker} gate: {exc}")
        return 0
    system = f"nearest-faq+{args.reranker}"
    report = evaluate(answerer, examples, system=system)

    grounding = GroundednessReport()
    for example in examples:
        answer = answerer.answer(example.question)
        if not answer.cited_spans:
            continue
        retrieved = [h.span for h in answerer.retrieve(example.question, route(example.question))]
        grounding.checks.extend(
            check_answer(answer, retrieved=retrieved, allowlist=answerer.allowlist)
        )

    current = snapshot(report, grounding, system=system)

    if args.update:
        write_baseline(current, baseline_path)
        print(f"baseline updated -> {baseline_path}")
        return 0

    previous = load_baseline(baseline_path)
    if previous is None:
        write_baseline(current, baseline_path)
        print(f"no baseline found; wrote initial baseline -> {baseline_path}")
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
