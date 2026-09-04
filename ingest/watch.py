"""Freshness: has the ground moved under the corpus?

This is the part that makes "accurate" a maintained property rather than a
launch-day claim. Indian compliance rarely breaks because a system invented law;
it breaks because a notification amended the position and the answer kept
quoting the old one, confidently and with a real citation.

The watcher re-fetches every collectable source and compares the normalised
content hash to what the corpus was built from. Three outcomes:

* **unchanged** - the source says the same thing it did at build time.
* **changed** - the page's readable text differs. Every span derived from it is
  marked ``needs_review``: not wrong, but no longer known to be right.
* **unreachable** - the fetch failed. Reported rather than silently treated as
  unchanged, because "we could not check" and "we checked and it is fine" are
  very different claims to make about legal text.

Separately, a span older than its source's ``refresh_days`` is ``stale`` even if
nothing changed - nobody has confirmed it recently enough to keep quoting it
without a flag.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ingest.build_corpus import load_spans
from ingest.fetch import Fetcher
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


def check(*, spans_path: Path | None = None) -> list[SourceFreshness]:
    allowlist = load_allowlist()
    spans = load_spans(spans_path) if spans_path else load_spans()
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for span in spans:
        hashes.setdefault(span.source_id, span.content_hash)
        counts[span.source_id] = counts.get(span.source_id, 0) + 1

    now = datetime.now(UTC).isoformat()
    report: list[SourceFreshness] = []
    with Fetcher() as fetcher:
        for entry in allowlist.fetchable():
            live = fetcher.fetch(entry, refresh=True)
            corpus_hash = hashes.get(entry.id, "")
            if not live.ok:
                verdict = "unreachable"
            elif not corpus_hash:
                verdict = "unindexed"
            else:
                verdict = "unchanged" if live.content_hash == corpus_hash else "changed"
            report.append(
                SourceFreshness(
                    source_id=entry.id,
                    verdict=verdict,
                    corpus_hash=corpus_hash,
                    live_hash=live.content_hash,
                    checked_at=now,
                    span_count=counts.get(entry.id, 0),
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
