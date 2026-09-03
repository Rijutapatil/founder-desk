"""Extract the facts that decide the answer - and refuse to guess them.

Three facts change what is true for an Indian founder, and getting any of them
wrong produces an answer that is confident, well-cited and wrong:

* **State.** Shops & Establishments registration, professional tax and stamp
  duty are state law. "Do I need to register my establishment?" has different
  answers in Maharashtra and Karnataka.
* **Entity type.** Thresholds, filings and eligibility differ across Pvt Ltd,
  LLP, OPC and sole proprietorship. DPIIT recognition, for instance, is open to
  a Pvt Ltd, an LLP and a registered partnership - and not to a proprietorship.
* **Turnover.** The GST registration threshold is a turnover test, and the
  special-category states use a different number.

The rule this module exists to enforce, borrowed from the router in the
hts-agent project: **null rather than a guess.** An unstated fact stays ``None``
and propagates to a clarifying question. Inferring "probably Maharashtra"
because the person mentioned Mumbai in passing is how a compliance tool becomes
dangerous.

Detection here is deterministic - keywords and patterns, no model. That is not a
placeholder for a smarter version: it keeps the whole evaluated path free to run
in CI with no key, and it makes routing behaviour reproducible in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.schema import Applicability, EntityType

# ISO 3166-2:IN code for each state, keyed by the names people actually type.
STATE_NAMES: dict[str, str] = {
    "andhra pradesh": "AP",
    "arunachal pradesh": "AR",
    "assam": "AS",
    "bihar": "BR",
    "chandigarh": "CH",
    "chhattisgarh": "CT",
    "delhi": "DL",
    "new delhi": "DL",
    "goa": "GA",
    "gujarat": "GJ",
    "haryana": "HR",
    "himachal pradesh": "HP",
    "jammu and kashmir": "JK",
    "jharkhand": "JH",
    "karnataka": "KA",
    "kerala": "KL",
    "ladakh": "LA",
    "madhya pradesh": "MP",
    "maharashtra": "MH",
    "manipur": "MN",
    "meghalaya": "ML",
    "mizoram": "MZ",
    "nagaland": "NL",
    "odisha": "OR",
    "puducherry": "PY",
    "punjab": "PB",
    "rajasthan": "RJ",
    "sikkim": "SK",
    "tamil nadu": "TN",
    "telangana": "TG",
    "tripura": "TR",
    "uttar pradesh": "UP",
    "uttarakhand": "UT",
    "west bengal": "WB",
}

# Cities are *not* used to infer a state. They are listed so the router can say
# "you mentioned Mumbai, but I need the state of the registered office" instead
# of quietly assuming - a company can be headquartered in one state and
# registered in another.
CITY_HINTS: frozenset[str] = frozenset(
    {
        "mumbai",
        "bengaluru",
        "bangalore",
        "delhi",
        "gurgaon",
        "gurugram",
        "noida",
        "hyderabad",
        "chennai",
        "pune",
        "kolkata",
        "ahmedabad",
        "jaipur",
        "kochi",
    }
)

ENTITY_PATTERNS: list[tuple[re.Pattern[str], EntityType]] = [
    (re.compile(r"\bopc\b|one[- ]person compan", re.I), EntityType.OPC),
    (re.compile(r"\bllp\b|limited liability partnership", re.I), EntityType.LLP),
    (re.compile(r"\bpvt\.? ?ltd\b|private limited|pvt-ltd", re.I), EntityType.PVT_LTD),
    (re.compile(r"sole[- ]propriet|proprietorship", re.I), EntityType.SOLE_PROP),
    (re.compile(r"\bpartnership firm\b|registered partnership", re.I), EntityType.PARTNERSHIP),
]

# Topics that are state law. A question touching these cannot be answered
# all-India, so an unknown state is a blocking gap rather than a nicety.
STATE_DEPENDENT = re.compile(
    r"shops?\s*(and|&)?\s*establishment|professional tax|\bptec\b|\bptrc\b|"
    r"stamp duty|labour licen[cs]e|state licen[cs]e",
    re.I,
)

# Questions asking for a recommendation rather than for what a source says.
JUDGEMENT = re.compile(
    r"\bshould i\b|\bwhich (is|one) (is )?better\b|\bwhat.s better\b|\bdo you recommend\b|"
    r"\bis it worth\b|\bbetter (to|for)\b|\bwhich should\b|\badvise me\b|\bwhat would you\b",
    re.I,
)

_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|cr)\b", re.I)


@dataclass(frozen=True)
class Routing:
    """What the router could establish, and what it could not."""

    applicability: Applicability
    needs_state: bool = False
    is_judgement: bool = False
    mentioned_cities: tuple[str, ...] = field(default=())

    @property
    def missing_state(self) -> bool:
        return self.needs_state and self.applicability.state is None

    def clarifying_question(self) -> str:
        """The specific fact needed - never a generic request for more detail."""
        if self.mentioned_cities:
            city = self.mentioned_cities[0].title()
            return (
                f"This depends on your state - the rules you are asking about are state law. "
                f"You mentioned {city}, but a company's registered office can sit in a different "
                f"state from where it operates, so I will not assume. Which state is the "
                f"registered office in?"
            )
        return (
            "This depends on your state - the rules you are asking about are state law, and "
            "they differ between states. Which state is the registered office in?"
        )


def detect_state(question: str) -> str | None:
    lowered = question.lower()
    # Longest name first, so "andhra pradesh" is not shadowed by a shorter match.
    for name in sorted(STATE_NAMES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return STATE_NAMES[name]
    return None


def detect_entity(question: str) -> EntityType | None:
    for pattern, entity in ENTITY_PATTERNS:
        if pattern.search(question):
            return entity
    return None


def detect_turnover(question: str) -> str | None:
    match = _AMOUNT.search(question)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).lower()
    crore = value if unit.startswith(("crore", "cr")) else value / 100
    return f"{crore:g} crore" if crore >= 1 else f"{crore * 100:g} lakh"


def route(
    question: str,
    *,
    state: str | None = None,
    entity: EntityType | None = None,
) -> Routing:
    """Explicit arguments win over anything inferred from the text."""
    resolved_state = state or detect_state(question)
    lowered = question.lower()
    is_judgement = bool(JUDGEMENT.search(question))

    # "Should I register an LLP or a Pvt Ltd" mentions an LLP without being
    # about one. Inferring an entity from a question that is *choosing between*
    # entities would make the answer claim it was answered for a structure the
    # asker has not adopted, so inference is suppressed here. An explicitly
    # passed entity still stands - that is a statement of fact, not a mention.
    resolved_entity = entity if entity else (None if is_judgement else detect_entity(question))

    return Routing(
        applicability=Applicability(
            entity_type=resolved_entity,
            state=resolved_state,
            turnover_band=detect_turnover(question),
        ),
        needs_state=bool(STATE_DEPENDENT.search(question)),
        is_judgement=is_judgement,
        mentioned_cities=tuple(c for c in CITY_HINTS if re.search(rf"\b{c}\b", lowered)),
    )
