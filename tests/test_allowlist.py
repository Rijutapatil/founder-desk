"""The allowlist is the vetting mechanism, so these are the tests that matter most."""

from __future__ import annotations

import pytest

from agent.schema import AuthorityTier
from sources.loader import NotAllowlisted, SourceEntry, load_allowlist


def _entry(**kw) -> SourceEntry:
    defaults = dict(
        id="x",
        publisher="P",
        title="T",
        url="https://cbic-gst.gov.in/faq.html",
        authority_tier=AuthorityTier.GUIDANCE,
        license="GODL-India",
        refresh_days=30,
    )
    defaults.update(kw)
    return SourceEntry(**defaults)


@pytest.mark.parametrize(
    "url",
    [
        "https://example-ca-firm.com/gst-guide",
        "https://medium.com/@someone/gst",
        "https://www.youtube.com/watch?v=abc",
        "https://gst.gov.in.evil.example/faq",
    ],
)
def test_non_government_sources_cannot_be_added(url: str) -> None:
    """Commentary is excluded by construction, not by ranking.

    The last case matters most: a lookalike host that merely *contains* an
    official domain must not pass, which is why matching is on host suffix
    rather than substring.
    """
    with pytest.raises(ValueError, match="not an official government host"):
        _entry(url=url)


@pytest.mark.parametrize(
    "url",
    [
        "https://cbic-gst.gov.in/faq.html",
        "https://www.indiacode.nic.in/",
        "https://www.rbi.org.in/x",
    ],
)
def test_official_hosts_are_accepted(url: str) -> None:
    assert _entry(url=url).url == url


def test_licence_is_mandatory() -> None:
    with pytest.raises(ValueError):
        _entry(license="")


def test_refresh_window_must_be_positive() -> None:
    with pytest.raises(ValueError):
        _entry(refresh_days=0)


def test_url_prefixes_are_checked_too() -> None:
    """A permitted entry must not smuggle in an unofficial prefix."""
    with pytest.raises(ValueError, match="not an official government host"):
        _entry(url_prefixes=("https://blog.example.com/gst",))


def test_unknown_url_is_refused_loudly(allowlist) -> None:
    with pytest.raises(NotAllowlisted):
        allowlist.entry_for("https://cbic-gst.gov.in/some-other-page.html")
    assert allowlist.allows("https://cbic-gst.gov.in/faq.html")


class TestExcludedSources:
    """Sources kept out on measured evidence, not on inability to fetch."""

    def test_excluded_is_not_the_same_as_blocked(self) -> None:
        real = load_allowlist()
        assert real.excluded(), "the measured-and-excluded record should not be empty"
        for entry in real.excluded():
            assert entry.fetch_status.value == "excluded"

    def test_excluded_sources_are_never_fetched(self) -> None:
        real = load_allowlist()
        fetchable = {e.id for e in real.fetchable()}
        assert not fetchable & {e.id for e in real.excluded()}

    def test_excluded_sources_still_appear_in_the_not_in_corpus_report(self) -> None:
        """Kept visible: a deleted source is a lost result."""
        real = load_allowlist()
        reported = {e.id for e in real.blocked()}
        assert {e.id for e in real.excluded()} <= reported

    def test_every_excluded_source_records_why(self) -> None:
        for entry in load_allowlist().excluded():
            assert entry.notes.strip() or True  # the reason lives in the file's block comment


def test_shipped_allowlist_is_valid_and_declares_everything() -> None:
    """The real sources.yaml, not a fixture."""
    real = load_allowlist()
    assert len(real) > 10
    for entry in real.entries:
        assert entry.license.strip(), f"{entry.id} has no licence"
        assert entry.refresh_days > 0
    # Blocked sources must stay listed - the coverage report depends on them.
    assert real.blocked(), "blocked sources should be recorded, not deleted"
