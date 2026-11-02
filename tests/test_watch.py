"""The weekly check tracks the indexed source text, not portal chrome."""

from __future__ import annotations

import pytest

from ingest import watch
from ingest.fetch import FetchResult, content_hash
from ingest.parse import build_spans
from tests.conftest import NOW, make_span

BODY = (
    "Registration is required when the prescribed threshold is crossed. "
    "The application must contain the company's legal name and address. "
    "The authority issues an acknowledgement after reviewing the application. "
) * 2


def test_span_digest_keeps_first_duplicate_id() -> None:
    first = make_span(text="Original answer")
    repeated = make_span(text="Different duplicate answer")
    assert watch.span_digest([first, repeated]) == watch.span_digest([first])


@pytest.mark.parametrize(
    ("live_text", "expected"),
    [
        (BODY + "\nLast updated 2 November 2026", "unchanged"),
        (BODY.replace("legal name", "registered name"), "changed"),
    ],
)
def test_check_ignores_page_chrome_but_detects_quoted_text_changes(
    monkeypatch: pytest.MonkeyPatch, allowlist, live_text: str, expected: str
) -> None:
    entry = allowlist.fetchable()[0]
    original = FetchResult(entry.id, entry.url, 200, NOW, BODY, content_hash(BODY), False)
    committed = build_spans(entry, original)
    live = FetchResult(entry.id, entry.url, 200, NOW, live_text, content_hash(live_text), False)

    class FakeFetcher:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def fetch(self, source, *, refresh):
            assert source.id == entry.id and refresh
            return live

    monkeypatch.setattr(watch, "load_allowlist", lambda: allowlist)
    monkeypatch.setattr(watch, "load_spans", lambda: committed)
    monkeypatch.setattr(watch, "Fetcher", FakeFetcher)

    result = watch.check()[0]
    assert result.verdict == expected
    assert result.corpus_hash == watch.span_digest(committed)
    assert result.live_hash == watch.span_digest(build_spans(entry, live))
