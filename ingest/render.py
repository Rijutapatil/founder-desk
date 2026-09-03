"""Headless rendering for sources that build their content in the browser.

Most of this corpus is served as HTML and needs nothing more than an HTTP GET.
A few official portals are single-page apps: NSWS returns 29 characters of
server HTML and assembles the page client-side, so a static fetcher sees an
empty shell no matter how many times it asks.

That is what blocked the incorporation domain. NSWS carries an official Ministry
of Corporate Affairs page describing incorporation of a company - who it applies
to, which Act and Rules govern it, how long it takes - and it was unreachable
for the same reason a screen reader without JavaScript would find it unreachable.

**This is not a way around a block.** The three hosts that return HTTP 403 to
automated clients still do so, and no browser User-Agent is substituted to get
past them: the renderer sends the same honest identifying User-Agent as the
plain fetcher. What it changes is only that JavaScript runs, so a page written
for a browser can be read. A site that declines to serve us still declines.

The dependency is heavy - a browser binary - so it is an optional extra and the
default install does not carry it. Sources needing it are marked `render: true`
in the allowlist and are reported as uncollectable, with an actionable message,
when the extra is absent. The committed corpus means CI never needs it.
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any

import structlog

log = structlog.get_logger(__name__)

INSTALL_HINT = (
    'headless rendering needs the optional browser extra: pip install -e ".[browser]" '
    "&& playwright install chromium"
)


class RendererUnavailable(RuntimeError):
    """Playwright or its browser is not installed."""


class Renderer:
    """Renders client-side pages, one at a time, at the same polite rate.

    The browser is launched once and reused: a cold Chromium start is a second
    or more, and paying it per page would make a full ingest run needlessly slow
    and needlessly heavy on the source.
    """

    def __init__(self, user_agent: str, *, rps: float = 1.0, timeout_ms: int = 45_000) -> None:
        self._user_agent = user_agent
        self._min_interval = 1.0 / rps if rps > 0 else 0.0
        self._timeout_ms = timeout_ms
        self._last_request = 0.0
        # Typed as Any: playwright is an optional dependency, so these cannot be
        # annotated with its classes without making the import mandatory.
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    def __enter__(self) -> Renderer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RendererUnavailable(INSTALL_HINT) from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on browser install
            raise RendererUnavailable(f"{INSTALL_HINT} ({type(exc).__name__})") from exc
        # Same identifying User-Agent as the plain fetcher. Running a browser is
        # about executing the page's own JavaScript, not about looking like
        # someone else.
        self._context = self._browser.new_context(user_agent=self._user_agent)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def render(self, url: str, selector: str | None = None) -> str:
        """Return the page's visible text after its scripts have run.

        ``selector`` narrows to the content region. A single-page app puts the
        entire site chrome inside ``<body>`` - helpdesk number, ministry
        navigation, translation notice, copyright - so taking the whole body
        wraps every span in a few hundred characters of boilerplate that is
        identical across pages. That is worse than untidy: repeated across a
        corpus it becomes common vocabulary, which drags on BM25 and dilutes the
        quote a reader actually sees. Naming the content region is cleaner than
        filtering the chrome out afterwards.
        """
        self._ensure()
        self._throttle()
        page: Any = self._context.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=self._timeout_ms)
            # networkidle can settle before the last render pass paints; a short
            # settle is cheaper than a flaky, half-empty capture.
            page.wait_for_timeout(2000)
            if selector:
                node: Any = page.query_selector(selector)
                if node is None:
                    # Report rather than silently falling back to the whole
                    # body: a selector that stopped matching means the portal
                    # was redesigned, and the corpus should be rebuilt
                    # deliberately rather than quietly refilled with chrome.
                    log.warning("selector_missed", url=url, selector=selector)
                    return ""
                selected: str = node.inner_text() or ""
                return selected
            text: str = page.inner_text("body")
            return text
        finally:
            page.close()

    def close(self) -> None:
        for attr in ("_context", "_browser"):
            obj: Any = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:  # pragma: no cover - best-effort teardown
                    log.warning("renderer_close_failed", component=attr)
                setattr(self, attr, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # pragma: no cover
                log.warning("renderer_close_failed", component="_playwright")
            self._playwright = None


def available() -> bool:
    """Whether headless rendering can run in this environment."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True
