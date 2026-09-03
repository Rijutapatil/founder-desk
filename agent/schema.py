"""The output contract.

Everything in this module exists to make one property true by construction:
**a claim cannot leave this system without a verbatim quote from an allowlisted
government source attached to it.**

That is enforced here, in validators, rather than in a prompt. A prompt is a
request; a validator is a guarantee. If the answering layer produces a claim it
cannot ground, constructing the :class:`Answer` raises - the failure surfaces as
an error rather than as confident prose.

Three ideas carry most of the weight:

* **Authority tier.** Indian compliance text comes in three legal weights, and
  they are not interchangeable. A portal FAQ is a helpful gloss on the CGST
  Rules; it is not the rule. Tier travels with every span so an answer can be
  audited for whether it leaned on guidance where a statute was needed.
* **Applicability.** Shops & Establishments, professional tax and stamp duty are
  *state* law, and thresholds vary by entity type. A span therefore records who
  it applies to, and an answer records who it was answered *for*. A generic
  answer to a state-specific question is the most common way to be confidently
  wrong here.
* **Freshness.** A citation that was right in March can be wrong in April. Every
  span carries the date of the instrument, the date it was fetched, and a hash
  of what was fetched, so staleness is a computable property rather than a hope.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Stamped onto every answer by a validator, so it cannot be dropped by a caller
# or edited away by a model. This tool reports what published sources say; it
# does not advise.
DISCLAIMER = (
    "INFORMATION GROUNDED IN PRIMARY SOURCES - NOT PROFESSIONAL ADVICE. "
    "Quotes are reproduced from official government publications and may have "
    "been amended since they were fetched. Nothing here replaces a qualified "
    "chartered accountant, company secretary or lawyer."
)


class AuthorityTier(IntEnum):
    """Legal weight of a source. Lower binds harder.

    The distinction is not pedantry. "The GST portal FAQ says X" and "Rule 8 of
    the CGST Rules says X" are different assertions, and when they disagree the
    rule wins. Recording the tier is what lets the eval ask whether an answer
    rested on guidance when a rule was available.
    """

    STATUTE = 1
    """Acts and Rules - Companies Act 2013, CGST Act and Rules, Income-tax Act."""

    INSTRUMENT = 2
    """Binding subordinate instruments - CBIC/CBDT notifications and circulars,
    RBI master directions. These amend the practical position constantly."""

    GUIDANCE = 3
    """Official guidance - portal FAQs, MCA/DPIIT/EPFO help pages. Authoritative
    as to the department's own position, but not law."""


class Domain(StrEnum):
    """The first-year compliance areas in scope for v1."""

    INCORPORATION = "incorporation"
    TAX_REGISTRATION = "tax_registration"
    GST = "gst"
    STARTUP_INDIA = "startup_india"
    BANKING_FEMA = "banking_fema"
    LABOUR = "labour"


class EntityType(StrEnum):
    PVT_LTD = "pvt-ltd"
    LLP = "llp"
    OPC = "opc"
    PARTNERSHIP = "partnership"
    SOLE_PROP = "sole-prop"


class SpanStatus(StrEnum):
    """Whether a span can still be relied on."""

    CURRENT = "current"
    NEEDS_REVIEW = "needs_review"
    """The upstream document changed since this span was extracted."""
    STALE = "stale"
    """Past its refresh window - nobody has confirmed it recently enough."""
    SUPERSEDED = "superseded"
    """A later instrument in the corpus replaced it."""


class AnswerKind(StrEnum):
    """What the system decided to do. Four outcomes, and only one is an answer."""

    GROUNDED = "grounded"
    """Every claim is quoted from a cited span."""
    CLARIFY = "clarify"
    """A decisive fact is missing (usually the state). Ask, do not generalise."""
    INFORMATIONAL_ONLY = "informational_only"
    """The question asks for professional judgement. Give factors and sources,
    never a recommendation."""
    REFUSED = "refused"
    """Nothing in the allowlisted corpus supports an answer. Say so, and say
    what was searched."""


# ISO 3166-2:IN subdivision codes. Kept explicit rather than free-text so a
# state-scoped span and a state-scoped question can actually be compared.
INDIAN_STATES: frozenset[str] = frozenset(
    {
        "AN",
        "AP",
        "AR",
        "AS",
        "BR",
        "CH",
        "CT",
        "DH",
        "DL",
        "GA",
        "GJ",
        "HP",
        "HR",
        "JH",
        "JK",
        "KA",
        "KL",
        "LA",
        "LD",
        "MH",
        "ML",
        "MN",
        "MP",
        "MZ",
        "NL",
        "OR",
        "PB",
        "PY",
        "RJ",
        "SK",
        "TG",
        "TN",
        "TR",
        "UP",
        "UT",
        "WB",
    }
)


class SourceSpan(BaseModel):
    """One retrievable, quotable unit of official text.

    Frozen: a span is a record of what a document said when it was fetched. If
    the document changes, that is a *new* span with a new hash, not a mutation
    of this one - which is what makes the freshness ledger meaningful.
    """

    model_config = ConfigDict(frozen=True)

    span_id: str
    source_id: str = Field(description="Allowlist entry this came from.")
    text: str = Field(description="Verbatim source text. Never paraphrased.")
    citation: str = Field(description="Human-readable citation, e.g. 'CGST Rules, Rule 8(1)'.")
    url: str
    publisher: str
    authority_tier: AuthorityTier
    domains: tuple[Domain, ...] = ()

    instrument_date: date | None = Field(
        default=None, description="Date of the instrument itself, where stated."
    )
    fetched_at: datetime
    content_hash: str = Field(description="Hash of the normalised source document.")

    char_start: int | None = None
    char_end: int | None = None

    states: tuple[str, ...] = Field(
        default=(), description="ISO 3166-2:IN codes. Empty means all-India."
    )
    entity_types: tuple[EntityType, ...] = Field(
        default=(), description="Empty means every entity type."
    )
    superseded_by: str | None = Field(
        default=None, description="span_id of the instrument that replaced this."
    )

    @model_validator(mode="after")
    def _check(self) -> SourceSpan:
        if not self.text.strip():
            raise ValueError(f"{self.span_id}: a span with no text cannot be quoted")
        unknown = set(self.states) - INDIAN_STATES
        if unknown:
            raise ValueError(f"{self.span_id}: unknown state codes {sorted(unknown)}")
        return self

    def applies_to(self, *, state: str | None, entity: EntityType | None) -> bool:
        """Whether this span governs the asker's situation.

        Empty scope means all-India / all entity types, so an unscoped span
        always applies. A *scoped* span with an unknown asker does not apply -
        that is deliberate, and it is what pushes the router to ask rather than
        letting a Maharashtra rule answer a Karnataka question.
        """
        if self.states and (state is None or state not in self.states):
            return False
        if self.entity_types and (entity is None or entity not in self.entity_types):
            return False
        return True

    def status(self, *, refresh_days: int, now: datetime | None = None) -> SpanStatus:
        """Freshness verdict for this span, as of ``now``."""
        if self.superseded_by is not None:
            return SpanStatus.SUPERSEDED
        moment = now or datetime.now(UTC)
        age = (moment - self.fetched_at).days
        return SpanStatus.STALE if age > refresh_days else SpanStatus.CURRENT


class CitedSpan(BaseModel):
    """A span as it appears in an answer - quotable and traceable."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    citation: str
    text: str
    url: str
    publisher: str
    authority_tier: AuthorityTier
    instrument_date: date | None = None
    fetched_at: datetime
    status: SpanStatus = SpanStatus.CURRENT

    @classmethod
    def of(cls, span: SourceSpan, status: SpanStatus = SpanStatus.CURRENT) -> CitedSpan:
        return cls(
            span_id=span.span_id,
            citation=span.citation,
            text=span.text,
            url=span.url,
            publisher=span.publisher,
            authority_tier=span.authority_tier,
            instrument_date=span.instrument_date,
            fetched_at=span.fetched_at,
            status=status,
        )


class Claim(BaseModel):
    """One assertion, and the spans that carry it.

    ``supported_by`` is not decorative. An answer is a list of claims, and a
    claim with no spans is a validation error, not a stylistic lapse.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    supported_by: tuple[str, ...] = Field(description="span_ids proving this claim.")

    @model_validator(mode="after")
    def _needs_support(self) -> Claim:
        if not self.supported_by:
            raise ValueError(f"ungrounded claim: {self.text!r}")
        return self


class Applicability(BaseModel):
    """Who an answer was answered *for*. Printed with every answer."""

    model_config = ConfigDict(frozen=True)

    entity_type: EntityType | None = None
    state: str | None = None
    turnover_band: str | None = None

    def describe(self) -> str:
        parts = [
            f"entity: {self.entity_type.value}" if self.entity_type else "entity: unspecified",
            f"state: {self.state}" if self.state else "state: all-India",
        ]
        if self.turnover_band:
            parts.append(f"turnover: {self.turnover_band}")
        return " · ".join(parts)


class Answer(BaseModel):
    """The only thing this system is allowed to return.

    The validator below is the whole point of the module: a ``GROUNDED`` answer
    with an unsupported claim, or with a claim pointing at a span that was never
    cited, cannot be constructed.
    """

    model_config = ConfigDict(frozen=True)

    kind: AnswerKind
    question: str
    applies_to: Applicability = Applicability()

    claims: tuple[Claim, ...] = ()
    cited_spans: tuple[CitedSpan, ...] = ()

    clarifying_question: str | None = None
    """Set when ``kind is CLARIFY`` - the specific fact needed, never a generic
    'please provide more detail'."""

    considerations: tuple[str, ...] = ()
    """Set when ``kind is INFORMATIONAL_ONLY`` - the factors a professional would
    weigh. Deliberately not a recommendation."""

    searched: tuple[str, ...] = ()
    """Set when ``kind is REFUSED`` - which sources were searched and came back
    empty. A refusal that does not say what it looked at is not auditable."""

    as_of: datetime | None = None
    disclaimer: str = DISCLAIMER

    @property
    def has_stale_citation(self) -> bool:
        return any(s.status is not SpanStatus.CURRENT for s in self.cited_spans)

    @model_validator(mode="after")
    def _enforce_grounding(self) -> Answer:
        # The disclaimer is re-stamped rather than trusted, so it survives a
        # caller constructing an Answer with it blanked or reworded.
        if self.disclaimer != DISCLAIMER:
            object.__setattr__(self, "disclaimer", DISCLAIMER)

        cited = {s.span_id for s in self.cited_spans}

        if self.kind is AnswerKind.GROUNDED:
            if not self.claims:
                raise ValueError("a grounded answer with no claims is not an answer")
            if not cited:
                raise ValueError("no cited span - a grounded answer must quote a source")
            for claim in self.claims:
                missing = set(claim.supported_by) - cited
                if missing:
                    raise ValueError(
                        f"claim {claim.text!r} cites {sorted(missing)}, which was never "
                        "included in cited_spans - fabricated citation"
                    )
        elif self.claims:
            raise ValueError(f"{self.kind.value} answers must not assert claims")

        if self.kind is AnswerKind.CLARIFY and not self.clarifying_question:
            raise ValueError("a clarify answer must name the fact it needs")
        if self.kind is AnswerKind.REFUSED and not self.searched:
            raise ValueError("a refusal must record what was searched")
        if self.kind is AnswerKind.INFORMATIONAL_ONLY and not self.considerations:
            raise ValueError("an informational answer must give the factors")
        return self
