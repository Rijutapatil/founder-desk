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
CERT_DIR = Path(__file__).parent / "certs"

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
    """Cannot be collected: a 403, a broken TLS chain, or a page with no content."""
    EXCLUDED = "excluded"
    """Collectable, in scope, and measured to make the system *worse*.

    Distinct from BLOCKED on purpose. "We could not fetch this" and "we fetched
    this, measured it, and it degraded the answers" are different facts about a
    source, and collapsing them would hide the more interesting one.
    """
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
    render: bool = Field(
        default=False,
        description=(
            "Page builds its content client-side, so collecting it needs a headless "
            "browser (the optional [browser] extra). Not a way past a block."
        ),
    )
    content_selector: str | None = Field(
        default=None,
        description=(
            "CSS selector for the page's content region. Rendered pages carry the whole "
            "site's header and footer in <body>; naming the content region is cleaner "
            "than filtering the chrome out afterwards."
        ),
    )
    ca_bundle: str | None = Field(
        default=None,
        description=(
            "Filename under sources/certs/ holding an intermediate certificate this host "
            "fails to send. Completes the chain; never disables verification."
        ),
    )
    license_verified: bool = Field(
        default=False,
        description="Whether a human has actually read this portal's terms. False is honest.",
    )

    url_prefixes: tuple[str, ...] = Field(
        default=(),
        description="Further URLs under this entry - e.g. the PDFs a landing page links to.",
    )
    notes: str = ""
    external_justification: str = Field(
        default="",
        description=(
            "Required for tier 4. Who publishes this and what relationship they have "
            "to the process it describes."
        ),
    )

    @model_validator(mode="after")
    def _ca_bundle_must_exist(self) -> SourceEntry:
        if self.ca_bundle is not None and not self.ca_bundle_path.exists():  # type: ignore[union-attr]
            raise ValueError(f"{self.id}: ca_bundle {self.ca_bundle!r} not found in {CERT_DIR}")
        return self

    @model_validator(mode="after")
    def _must_be_official(self) -> SourceEntry:
        """Non-government hosts are admissible only as a declared exception.

        The rule is not "official hosts only" any more - it is that leaving an
        official host is a decision someone made in writing. A source off a
        government domain must be tier 4 *and* must say, in this file, why it
        belongs: which body it is and what relationship it has to the process.
        A professional firm writing about a subject has no such relationship,
        so there is nothing it could put in that field.
        """
        if self.authority_tier is AuthorityTier.EXTERNAL:
            if not self.external_justification.strip():
                raise ValueError(
                    f"{self.id}: an external source must state why it is admitted "
                    "in `external_justification` - who publishes it and what "
                    "relationship they have to the process."
                )
            return self

        for candidate in (self.url, *self.url_prefixes):
            host = (urlparse(candidate).hostname or "").lower()
            if not host:
                raise ValueError(f"{self.id}: {candidate!r} has no host")
            if not any(host == s.lstrip(".") or host.endswith(s) for s in OFFICIAL_HOST_SUFFIXES):
                raise ValueError(
                    f"{self.id}: {host!r} is not an official government host. "
                    f"Allowed suffixes: {', '.join(OFFICIAL_HOST_SUFFIXES)}. "
                    "Set authority_tier: 4 and fill external_justification to admit it "
                    "deliberately; commentary and professional-firm content still do not qualify."
                )
        return self

    @property
    def ca_bundle_path(self) -> Path | None:
        """Absolute path to this entry's extra CA certificate, if it needs one.

        Some government hosts are misconfigured: they serve only their leaf
        certificate and omit the intermediate, so the chain cannot be built from
        a normal trust store. ESIC does this.

        The fix is to supply the missing intermediate, **not** to turn
        verification off. Validation still terminates at a root already trusted
        by certifi, so a tampered response is still rejected - which matters
        more here than anywhere, because this text gets quoted as law. The
        certificate is committed and its fingerprint pinned by a test, so a
        substituted one fails the build rather than passing silently.
        """
        if self.ca_bundle is None:
            return None
        return CERT_DIR / self.ca_bundle

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

    def external(self) -> list[SourceEntry]:
        """Sources that are not government publications. Reported, never hidden."""
        return [e for e in self._entries if e.authority_tier is AuthorityTier.EXTERNAL]

    def by_domain(self, domain: Domain) -> list[SourceEntry]:
        return [e for e in self._entries if domain in e.domains]

    def fetchable(self) -> list[SourceEntry]:
        """Entries ingestion may actually attempt."""
        return [e for e in self._entries if e.fetch_status is FetchStatus.OK]

    def blocked(self) -> list[SourceEntry]:
        """Entries that are in scope but not in the corpus. Reported, never hidden."""
        return [
            e
            for e in self._entries
            if e.fetch_status in (FetchStatus.BLOCKED, FetchStatus.EXCLUDED)
        ]

    def excluded(self) -> list[SourceEntry]:
        """Collectable sources deliberately left out on measured evidence."""
        return [e for e in self._entries if e.fetch_status is FetchStatus.EXCLUDED]


def load_allowlist(path: Path = DEFAULT_ALLOWLIST) -> Allowlist:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = [SourceEntry.model_validate(item) for item in raw.get("sources", [])]
    if not entries:
        raise ValueError(f"{path} lists no sources")
    return Allowlist(entries)
