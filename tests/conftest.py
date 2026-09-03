from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent.schema import AuthorityTier, Domain, SourceSpan
from sources.loader import Allowlist, SourceEntry

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def make_span(
    span_id: str = "src:a", text: str = "Do I need to register? Yes, you do.", **kw
) -> SourceSpan:
    defaults = dict(
        span_id=span_id,
        source_id=span_id.split(":")[0],
        text=text,
        citation="Test source - Q: registration",
        url="https://cbic-gst.gov.in/faq.html",
        publisher="CBIC",
        authority_tier=AuthorityTier.GUIDANCE,
        domains=(Domain.GST,),
        fetched_at=NOW,
        content_hash="abc123",
    )
    defaults.update(kw)
    return SourceSpan(**defaults)


@pytest.fixture
def allowlist() -> Allowlist:
    return Allowlist(
        [
            SourceEntry(
                id="src",
                publisher="CBIC",
                title="Test source",
                url="https://cbic-gst.gov.in/faq.html",
                authority_tier=AuthorityTier.GUIDANCE,
                license="GODL-India",
                refresh_days=90,
                domains=(Domain.GST,),
            )
        ]
    )
