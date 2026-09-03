"""Fetch, parse and persist the corpus.

One command turns the allowlist into `data/corpus/spans.jsonl` plus a coverage
report. Everything downstream - retrieval, the eval, the CLI - reads that file
and never touches the network, which is what lets the whole measured path run in
CI with no credentials.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import structlog

from agent.schema import Domain, SourceSpan
from ingest.fetch import fetch_all
from ingest.parse import build_all
from sources.loader import Allowlist, load_allowlist

log = structlog.get_logger(__name__)

CORPUS_DIR = Path("data/corpus")
SPANS_PATH = CORPUS_DIR / "spans.jsonl"


def write_spans(spans: list[SourceSpan], path: Path = SPANS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for span in spans:
            fh.write(span.model_dump_json() + "\n")


def load_spans(path: Path = SPANS_PATH) -> list[SourceSpan]:
    """Load the built corpus. Returns empty on a fresh clone rather than raising.

    A missing corpus is a normal state - it is regenerable and not committed -
    so callers decide whether that is fatal. The CI gate treats it as "skip",
    the CLI treats it as "tell the user to run the build".
    """
    if not path.exists():
        return []
    return [SourceSpan.model_validate_json(line) for line in path.read_text().splitlines() if line]


def coverage(spans: list[SourceSpan], allowlist: Allowlist) -> str:
    """Human-readable coverage, including what is missing and why."""
    per_domain: Counter[str] = Counter()
    for span in spans:
        for domain in span.domains:
            per_domain[domain.value] += 1

    lines = ["", "coverage by domain", "-" * 58]
    for domain in Domain:
        entries = allowlist.by_domain(domain)
        blocked = [e for e in entries if e.fetch_status.value == "blocked"]
        note = f"  ({len(blocked)} source(s) blocked)" if blocked else ""
        lines.append(f"  {domain.value:<18} {per_domain.get(domain.value, 0):>5} spans{note}")

    if allowlist.blocked():
        lines += ["", "in scope but not collectable", "-" * 58]
        lines += [f"  {e.id:<32} {e.publisher[:40]}" for e in allowlist.blocked()]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-fetch, ignoring the cache")
    parser.add_argument("--out", type=Path, default=SPANS_PATH)
    args = parser.parse_args()

    allowlist = load_allowlist()
    results = fetch_all(allowlist, refresh=args.refresh)
    spans = build_all(allowlist.fetchable(), results)
    write_spans(spans, args.out)

    by_source = Counter(s.source_id for s in spans)
    print(f"\n{len(spans)} spans from {len(by_source)} sources -> {args.out}")
    for source_id, n in by_source.most_common():
        print(f"  {source_id:<34} {n:>5}")
    print(coverage(spans, allowlist))
    return 0 if spans else 1


if __name__ == "__main__":
    sys.exit(main())
