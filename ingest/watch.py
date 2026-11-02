"""Freshness: has the ground moved under the corpus?

This is the part that makes "accurate" a maintained property rather than a
launch-day claim. Indian compliance rarely breaks because a system invented law;
it breaks because a notification amended the position and the answer kept
quoting the old one, confidently and with a real citation.

The watcher re-fetches every collectable source and compares the quotable spans
to what the corpus was built from. Page chrome changes frequently, so hashing
the entire page would make the weekly check noisy. Four outcomes:

* **unchanged** - the source says the same thing it did at build time.
* **changed** - a quotable span differs. Spans from that source need review:
  not necessarily wrong, but no longer known to be right.
* **unreachable** - the fetch failed. Reported rather than silently treated as
  unchanged, because "we could not check" and "we checked and it is fine" are
  very different claims to make about legal text.
* **unindexed** - the source has no committed spans to compare yet.

Separately, a span older than its source's ``refresh_days`` is ``stale`` even if
nothing changed - nobody has confirmed it recently enough to keep quoting it
without a flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent.schema import SourceSpan
from ingest.build_corpus import load_spans
from ingest.fetch import Fetcher, normalise
from ingest.parse import build_spans
from sources.loader import load_allowlist

FRESHNESS_PATH = Path(__file__).resolve().parent.parent / "sources" / "freshness.json"


@dataclass(frozen=True)
class SourceFreshness:
    source_id: str
    verdict: str  # unchanged | changed | unreachable
    corpus_hash: str
    live_hash: str
    checked_at: str
    span_count: int


def span_digest(spans: list[SourceSpan]) -> str:
    """Hash the indexed text, ignoring ordering and duplicate spans."""
    # build_all keeps the first span for an id. Mirror that rule here: a page
    # can repeat a question with different surrounding text later on.
    by_id: dict[str, str] = {}
    for span in spans:
        by_id.setdefault(span.span_id, normalise(span.text))
    texts = sorted(by_id.values())
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16] if texts else ""


def check(*, spans_path: Path | None = None) -> list[SourceFreshness]:
    allowlist = load_allowlist()
    spans = load_spans(spans_path) if spans_path else load_spans()
    by_source: dict[str, list[SourceSpan]] = {}
    for span in spans:
        by_source.setdefault(span.source_id, []).append(span)

    now = datetime.now(UTC).isoformat()
    report: list[SourceFreshness] = []
    with Fetcher() as fetcher:
        for entry in allowlist.fetchable():
            live = fetcher.fetch(entry, refresh=True)
            committed = by_source.get(entry.id, [])
            corpus_hash = span_digest(committed)
            if not live.ok:
                verdict = "unreachable"
            elif not corpus_hash:
                verdict = "unindexed"
            else:
                live_spans = build_spans(entry, live)
                live_hash = span_digest(live_spans)
                verdict = "unchanged" if live_hash == corpus_hash else "changed"
            report.append(
                SourceFreshness(
                    source_id=entry.id,
                    verdict=verdict,
                    corpus_hash=corpus_hash,
                    live_hash=live_hash if live.ok and corpus_hash else "",
                    checked_at=now,
                    span_count=len(committed),
                )
            )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="exit non-zero if any source moved (used by the scheduled CI job)",
    )
    args = parser.parse_args()

    report = check()
    FRESHNESS_PATH.write_text(json.dumps([asdict(r) for r in report], indent=2))

    changed = [r for r in report if r.verdict == "changed"]
    unreachable = [r for r in report if r.verdict == "unreachable"]
    for r in report:
        print(f"  {r.verdict:<12} {r.source_id:<34} {r.span_count:>4} spans")
    print(f"\n{len(changed)} changed, {len(unreachable)} unreachable, {len(report)} checked")
    if changed:
        print("\nspans from these sources are now needs_review:")
        for r in changed:
            print(f"  {r.source_id}: {r.corpus_hash} -> {r.live_hash}")
    return 1 if (args.fail_on_change and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
