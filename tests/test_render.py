"""Headless rendering: configuration, and degrading without a browser.

These tests deliberately do not launch a browser or touch the network. The
browser is an optional extra and CI does not install it, so a test suite that
needed one would either be skipped everywhere it matters or make the extra
mandatory in practice.
"""

from __future__ import annotations

import pytest

from agent.schema import AuthorityTier, Domain
from ingest.fetch import Fetcher
from ingest.render import INSTALL_HINT, RendererUnavailable, available
from sources.loader import SourceEntry, load_allowlist


def _rendered_entry(**kw) -> SourceEntry:
    defaults = dict(
        id="nsws-test",
        publisher="NSWS",
        title="T",
        url="https://www.nsws.gov.in/portal/approval-details/x",
        authority_tier=AuthorityTier.GUIDANCE,
        license="GoI",
        refresh_days=90,
        domains=(Domain.INCORPORATION,),
        render=True,
        content_selector=".marketplace-content",
    )
    defaults.update(kw)
    return SourceEntry(**defaults)


def test_rendered_sources_are_still_subject_to_the_allowlist() -> None:
    """Rendering changes how a page is read, never which pages may be read."""
    with pytest.raises(ValueError, match="not an official government host"):
        _rendered_entry(url="https://example-ca-firm.com/incorporation")


def test_render_and_selector_are_opt_in() -> None:
    plain = SourceEntry(
        id="x",
        publisher="P",
        title="T",
        url="https://cbic-gst.gov.in/faq.html",
        authority_tier=AuthorityTier.GUIDANCE,
        license="GoI",
        refresh_days=30,
    )
    assert plain.render is False
    assert plain.content_selector is None


def test_a_missing_browser_is_reported_not_raised(monkeypatch) -> None:
    """One uninstalled extra must not take down a whole ingest run.

    The other sources collect fine without a browser, so the run continues and
    this source is reported as uncollectable - with the command that fixes it.
    """
    entry = _rendered_entry()

    class Unavailable:
        def render(self, url: str, selector: str | None = None) -> str:
            raise RendererUnavailable(INSTALL_HINT)

        def close(self) -> None: ...

    with Fetcher(cache_dir=__import__("pathlib").Path("/tmp/founder-desk-test-cache")) as fetcher:
        fetcher._renderer = Unavailable()  # type: ignore[assignment]
        result = fetcher.fetch(entry, refresh=True)

    assert not result.ok
    assert result.status == 0
    assert result.text == ""


def test_the_install_hint_names_both_steps() -> None:
    """pip install alone is not enough - the browser binary is a separate download."""
    assert "browser" in INSTALL_HINT
    assert "playwright install" in INSTALL_HINT


def test_available_reports_the_environment_truthfully() -> None:
    assert available() is (__import__("importlib").util.find_spec("playwright") is not None)


class TestShippedRenderedSources:
    """The real allowlist entries that need a browser."""

    def test_every_rendered_source_names_a_content_region(self) -> None:
        """Taking the whole body wraps every span in site chrome.

        Repeated across a corpus that boilerplate becomes common vocabulary,
        which drags on BM25 and dilutes the quote a reader sees.
        """
        for entry in load_allowlist().entries:
            if entry.render:
                assert entry.content_selector, f"{entry.id} renders but takes the whole body"

    def test_rendering_is_not_used_on_hosts_that_refused_us(self) -> None:
        """The line this feature must not cross.

        Three hosts return 403 to automated clients. A browser would very likely
        get past that, and doing so would be working around a refusal rather
        than reading a page written for a browser. They stay blocked.
        """
        refused = {"mca-portal", "indiacode-companies-act", "labour-ministry"}
        for entry in load_allowlist().entries:
            if entry.id in refused:
                assert not entry.render, f"{entry.id} refused us; do not render around it"
