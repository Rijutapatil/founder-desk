"""Enumerate the NSWS approval catalogue for a ministry.

NSWS lists every central approval, but the catalogue is a paginated React
listing whose links load one ministry at a time behind a filter panel. There is
no URL that selects a ministry, so the only way to see what exists is to drive
the filter the way a person would.

This is a **discovery** tool, not part of ingestion. It prints candidate URLs;
a human reads them, decides which are in scope, and adds those to
``sources/sources.yaml`` by hand. That separation is deliberate: the allowlist is
what makes "official sources only" a property of the code rather than a promise,
and a crawler that could append to it would quietly become the thing deciding
what this system reads.

    python -m ingest.discover_nsws --ministry "Ministry of Corporate Affairs"

Needs the browser extra. It is not run in CI and not run during a build.
"""

from __future__ import annotations

import argparse
import sys

from ingest.fetch import USER_AGENT
from ingest.render import INSTALL_HINT

LISTING = "https://www.nsws.gov.in/portal/approvalsandregistrations"
FILTER_SELECTOR = "[class*=filter] label, [class*=Filter] label"


def discover(ministry: str, *, settle_ms: int = 3500) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - depends on install extras
        raise SystemExit(INSTALL_HINT) from None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_context(user_agent=USER_AGENT).new_page()
        try:
            page.goto(LISTING, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(settle_ms)

            target = next(
                (
                    label
                    for label in page.query_selector_all(FILTER_SELECTOR)
                    if (label.inner_text() or "").strip().startswith(ministry)
                ),
                None,
            )
            if target is None:
                raise SystemExit(f"no filter found for {ministry!r}")

            target.click()
            page.wait_for_timeout(settle_ms)
            hrefs = page.eval_on_selector_all(
                "a[href*='approval-details']", "els => els.map(e => e.getAttribute('href'))"
            )
            return sorted({f"https://www.nsws.gov.in{h}" for h in hrefs if h})
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ministry", required=True, help='e.g. "Ministry of Corporate Affairs"')
    args = parser.parse_args()

    urls = discover(args.ministry)
    print(f"{len(urls)} approvals listed for {args.ministry}\n")
    for url in urls:
        print(f"  {url}")
    print("\nThese are candidates, not sources. Add the in-scope ones to sources/sources.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
