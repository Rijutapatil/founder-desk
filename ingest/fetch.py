"""Collect the allowlisted sources.

Collection etiquette, carried over from the hts-agent project and applied here
for the same reason: these are public services run by government departments,
not APIs anyone is paying for.

* **One request per second**, serialised. Nothing here is urgent.
* **An honest User-Agent** naming the project and a contact address, so an
  administrator who sees the traffic can find out what it is.
* **Cached and resumable.** A re-run costs nothing for what is already on disk,
  which means development iterations do not re-hammer the source.

The content hash is taken over *extracted text with whitespace normalised*,
not over raw bytes. Government portals rewrite markup, rotate session tokens and
stamp build ids into their HTML constantly; hashing bytes would report a change
on every single fetch and the freshness signal would be pure noise. Hashing the
readable text means a hash change is a real change in what the page says.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import certifi
import httpx
import structlog

from sources.loader import Allowlist, SourceEntry, load_allowlist

log = structlog.get_logger(__name__)

USER_AGENT = "founder-desk/0.1 (portfolio research project; contact: preety.rijuta@gmail.com)"
REQUESTS_PER_SECOND = 1.0
DEFAULT_CACHE = Path("data/raw")

_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse whitespace so the hash tracks meaning, not markup."""
    return _WS.sub(" ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()[:16]


def extract_text(html: str) -> str:
    """Readable text from an HTML page.

    Scripts, styles and navigation chrome are dropped. BeautifulSoup is an
    optional dependency, so a plain-regex fallback keeps the module importable
    for anyone who installed the core package only - the fallback is worse, and
    says so, rather than failing at import time.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - exercised only without [ingest]
        log.warning("bs4_missing", detail="falling back to regex strip; install .[ingest]")
        return normalise(re.sub(r"<[^>]+>", " ", html))

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    # Block structure is preserved as newlines. Collapsing everything to one
    # line would be fine for hashing but destroys the only signal the FAQ parser
    # has: these pages mark a question and its answer as separate blocks, not
    # with any consistent punctuation.
    lines = (normalise(line) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    url: str
    status: int
    fetched_at: datetime
    text: str
    content_hash: str
    from_cache: bool

    @property
    def ok(self) -> bool:
        return self.status == 200 and len(self.text) > 200


class Fetcher:
    """Rate-limited, cached HTTP collection for allowlisted sources only."""

    def __init__(
        self, cache_dir: Path = DEFAULT_CACHE, *, rps: float = REQUESTS_PER_SECOND
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._min_interval = 1.0 / rps if rps > 0 else 0.0
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )
        # Hosts needing an extra intermediate get their own client, because the
        # trust store is fixed when the client is built. Cached so a run does not
        # rebuild an SSL context per request.
        self._pinned: dict[str, httpx.Client] = {}

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()
        for client in self._pinned.values():
            client.close()

    def _client_for(self, entry: SourceEntry) -> httpx.Client:
        """The client to use for this source.

        Entries with a ``ca_bundle`` get a context that trusts the normal root
        store *plus* the intermediate their server omits. This adds a link to
        the chain; it does not lower the bar. ``verify=False`` appears nowhere
        in this project, deliberately - a response that cannot be authenticated
        must not be quoted as law.
        """
        bundle = entry.ca_bundle_path
        if bundle is None:
            return self._client
        if entry.ca_bundle not in self._pinned:
            context = ssl.create_default_context(cafile=certifi.where())
            context.load_verify_locations(cafile=str(bundle))
            self._pinned[str(entry.ca_bundle)] = httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
                verify=context,
            )
        return self._pinned[str(entry.ca_bundle)]

    def _paths(self, entry: SourceEntry) -> tuple[Path, Path]:
        stem = self.cache_dir / entry.id
        return stem.with_suffix(".txt"), stem.with_suffix(".json")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def fetch(self, entry: SourceEntry, *, refresh: bool = False) -> FetchResult:
        body_path, meta_path = self._paths(entry)

        if not refresh and body_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            return FetchResult(
                source_id=entry.id,
                url=entry.url,
                status=meta["status"],
                fetched_at=datetime.fromisoformat(meta["fetched_at"]),
                text=body_path.read_text(encoding="utf-8"),
                content_hash=meta["content_hash"],
                from_cache=True,
            )

        self._throttle()
        now = datetime.now(UTC)
        try:
            response = self._client_for(entry).get(entry.url)
            status = response.status_code
            text = extract_text(response.text) if status == 200 else ""
        except httpx.HTTPError as exc:
            log.warning("fetch_failed", source=entry.id, error=type(exc).__name__)
            status, text = 0, ""

        result = FetchResult(
            source_id=entry.id,
            url=entry.url,
            status=status,
            fetched_at=now,
            text=text,
            content_hash=content_hash(text) if text else "",
            from_cache=False,
        )
        if result.ok:
            body_path.write_text(text, encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "source_id": entry.id,
                        "url": entry.url,
                        "status": status,
                        "fetched_at": now.isoformat(),
                        "content_hash": result.content_hash,
                        "chars": len(text),
                    },
                    indent=2,
                )
            )
        return result


def fetch_all(
    allowlist: Allowlist,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    limit: int | None = None,
    refresh: bool = False,
) -> list[FetchResult]:
    """Fetch every collectable source. Blocked entries are reported, not attempted."""
    for entry in allowlist.blocked():
        log.info("skipped_blocked", source=entry.id, detail="403 to automated clients")

    targets = allowlist.fetchable()[:limit] if limit else allowlist.fetchable()
    results: list[FetchResult] = []
    with Fetcher(cache_dir) as fetcher:
        for entry in targets:
            result = fetcher.fetch(entry, refresh=refresh)
            log.info(
                "fetched",
                source=entry.id,
                status=result.status,
                chars=len(result.text),
                cached=result.from_cache,
            )
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="ignore the cache")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    allowlist = load_allowlist()
    results = fetch_all(allowlist, cache_dir=args.cache, limit=args.limit, refresh=args.refresh)

    ok = [r for r in results if r.ok]
    print(
        f"\nfetched {len(ok)}/{len(results)} sources, {sum(len(r.text) for r in ok):,} characters"
    )
    for r in results:
        mark = "ok " if r.ok else "FAIL"
        print(f"  {mark} {r.source_id:<32} {r.status} {len(r.text):>8,} chars")
    for entry in allowlist.blocked():
        print(f"  skip {entry.id:<32} blocked - {entry.notes.splitlines()[0][:50]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
