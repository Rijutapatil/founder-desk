"""The allowlist: the only path into the index.

"Vetted by official sources only" is a claim, and a claim that lives in a README
is worth nothing. Here it is a data structure with a validator, so the property
is enforced rather than asserted:

* **A source must be published on an official Indian government host.** Host
  suffixes are checked against :data:`OFFICIAL_HOST_SUFFIXES`. A CA firm's blog,
  a news site or a YouTube transcript cannot be added to ``sources.yaml`` even
  by someone who wants to - the loader raises. This is the difference between
  "we prefer official sources" and "only official sources are representable".
* **A source must declare its licence.** Most Government of India content is
  under GODL-India, but not all of it, and some portals carry their own terms.
  A blank licence field fails validation, so the repo cannot quietly mirror
  content nobody checked the terms for.
* **A source must declare a refresh window.** Indian compliance changes by
  notification, continuously. A source with no stated staleness horizon would
  silently rot; requiring the field forces the question to be answered per
  source, with statutes given long windows and notification streams short ones.

Nothing else in the codebase is permitted to construct a fetch target. Ingestion
takes an :class:`Allowlist` and iterates it; there is no code path that accepts a
bare URL.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.schema import AuthorityTier, Domain, EntityType

DEFAULT_ALLOWLIST = Path(__file__).parent / "sources.yaml"

# Hosts whose content is a government publication. ``rbi.org.in`` is the one
# non-.gov.in entry and it is deliberate: the Reserve Bank publishes its master
# directions there and nowhere else.
OFFICIAL_HOST_SUFFIXES: tuple[str, ...] = (
    ".gov.in",
    ".nic.in",
    "rbi.org.in",
)


class FetchStatus(StrEnum):
    """Whether this source can actually be collected.

    ``BLOCKED`` is not a bug to be worked around. Several Indian government
    portals - MCA and India Code among them - return 403 to any non-browser
    client, and ESIC serves an incomplete TLS chain. They stay in the allowlist
    with this status because the alternative is worse: silently omitting them
    would make the corpus look complete when the incorporation domain is in fact
    under-covered. Ingestion skips them and reports them, and the README names
    the gap.

    Note what is *not* done about it. Neither spoofing a browser User-Agent nor
    disabling certificate verification is used to get past these. The first
    misrepresents the client to a public service that has said no; the second
    would make a tampered response indistinguishable from a real one, which is
    an unacceptable trade for text the system will quote as law.
    """

    OK = "ok"
    BLOCKED = "blocked"
    UNTESTED = "untested"


class NotAllowlisted(ValueError):
    """Raised when something tries to index a URL that is not on the allowlist."""


class SourceEntry(BaseModel):
    """One official publication the system is permitted to read."""

    model_config = ConfigDict(frozen=True)

    id: str
    publisher: str
    title: str
    url: str
    authority_tier: AuthorityTier
    license: str = Field(min_length=1, description="Licence or terms under which this is reused.")
    refresh_days: int = Field(gt=0, description="How long a fetch stays trustworthy.")

    domains: tuple[Domain, ...] = ()
    states: tuple[str, ...] = Field(default=(), description="Empty means all-India.")
    entity_types: tuple[EntityType, ...] = ()

    fetch_status: FetchStatus = FetchStatus.OK
    license_verified: bool = Field(
        default=False,
        description="Whether a human has actually read this portal's terms. False is honest.",
    )

    url_prefixes: tuple[str, ...] = Field(
        default=(),
        description="Further URLs under this entry - e.g. the PDFs a landing page links to.",
    )
    notes: str = ""

    @model_validator(mode="after")
    def _must_be_official(self) -> SourceEntry:
        for candidate in (self.url, *self.url_prefixes):
            host = (urlparse(candidate).hostname or "").lower()
            if not host:
                raise ValueError(f"{self.id}: {candidate!r} has no host")
            if not any(host == s.lstrip(".") or host.endswith(s) for s in OFFICIAL_HOST_SUFFIXES):
                raise ValueError(
                    f"{self.id}: {host!r} is not an official government host. "
                    f"Allowed suffixes: {', '.join(OFFICIAL_HOST_SUFFIXES)}. "
                    "Commentary, news and professional-firm content are out of scope by design."
                )
        return self

    def covers(self, url: str) -> bool:
        return url == self.url or any(url.startswith(p) for p in self.url_prefixes)


class Allowlist:
    """The loaded allowlist, and the single authority on what may be indexed."""

    def __init__(self, entries: list[SourceEntry]) -> None:
        seen: set[str] = set()
        for entry in entries:
            if entry.id in seen:
                raise ValueError(f"duplicate source id: {entry.id}")
            seen.add(entry.id)
        self._entries = entries
        self._by_id = {e.id: e for e in entries}

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Any:
        return iter(self._entries)

    @property
    def entries(self) -> list[SourceEntry]:
        return list(self._entries)

    def get(self, source_id: str) -> SourceEntry:
        try:
            return self._by_id[source_id]
        except KeyError:
            raise NotAllowlisted(f"unknown source id: {source_id}") from None

    def entry_for(self, url: str) -> SourceEntry:
        """The entry covering ``url``, or raise.

        Deliberately raises rather than returning ``None``: every caller of this
        is about to index something, and a silent ``None`` would invite an
        ``if entry:`` that skips the check.
        """
        for entry in self._entries:
            if entry.covers(url):
                return entry
        raise NotAllowlisted(
            f"{url} is not on the allowlist. Add it to sources/sources.yaml with a "
            "publisher, authority tier, licence and refresh window, or do not index it."
        )

    def allows(self, url: str) -> bool:
        try:
            self.entry_for(url)
        except NotAllowlisted:
            return False
        return True

    def by_domain(self, domain: Domain) -> list[SourceEntry]:
        return [e for e in self._entries if domain in e.domains]

    def fetchable(self) -> list[SourceEntry]:
        """Entries ingestion may actually attempt."""
        return [e for e in self._entries if e.fetch_status is FetchStatus.OK]

    def blocked(self) -> list[SourceEntry]:
        """Entries that are in scope but cannot be collected. Reported, never hidden."""
        return [e for e in self._entries if e.fetch_status is FetchStatus.BLOCKED]


def load_allowlist(path: Path = DEFAULT_ALLOWLIST) -> Allowlist:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = [SourceEntry.model_validate(item) for item in raw.get("sources", [])]
    if not entries:
        raise ValueError(f"{path} lists no sources")
    return Allowlist(entries)
