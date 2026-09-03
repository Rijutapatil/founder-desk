"""Turn fetched pages into quotable spans.

Two strategies, chosen per document by what the document actually is:

**FAQ pairing.** Most of this corpus is departmental Q&A, and it arrives in a
consistent shape: a line ending in a question mark, followed by the answer as
one or more blocks, until the next question. That structure is worth exploiting
rather than chunking over, for two reasons. A Q&A pair is a *semantically
complete unit* - chunking by character count would routinely split a question
from its answer and produce spans that retrieve well and quote uselessly. And
the question is written in the language a person actually uses, which makes the
pair simultaneously a corpus span and a labelled evaluation example.

Two FAQ layouts turn up, and the difference matters. Departmental FAQ pages are
often rendered as a two-column *table* whose cells are hard-wrapped, so a single
question arrives as several blocks and the naive "a block ending in ? is the
question" rule captures only its last fragment - producing a span whose question
reads "payable?". Those tables are delimited by a bare row number, which is the
reliable signal, so indexed parsing is tried first and question-mark pairing is
the fallback for pages that have no numbering.

**Prose chunking.** Statute pages have no Q&A structure, so they are chunked on
block boundaries with a character budget and a one-block overlap, so a sentence
that straddles a boundary still appears whole in one of the two spans.

Navigation chrome is the main adversary in both. Government portals wrap their
content in language switchers, breadcrumb trails and link menus, and a naive
extraction turns that into hundreds of two-word spans that dominate BM25 - short
documents score well on term-frequency normalisation. The filters below drop it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from agent.schema import Domain, SourceSpan
from ingest.fetch import FetchResult
from sources.loader import SourceEntry

# A question is a block ending in '?'. Long ones are prose that happens to end
# in a question mark, not a heading.
_MAX_QUESTION_CHARS = 320
_MIN_ANSWER_CHARS = 40
# The last Q&A on a page has no following question to stop at, so without a cap
# it absorbs the entire footer - cookie notices, password rules, the visitor
# counter. Observed on the Startup India FAQ, where the final answer ran to
# 6,000 characters of site chrome. Both guards below exist for that one case,
# and both are needed: the length cap alone would still admit 1,200 characters
# of menu.
_MAX_ANSWER_CHARS = 1400
_FOOTER = re.compile(
    r"terms of use|privacy policy|site ?map|all rights reserved|please login|"
    r"toll free number|your password must contain|subscribe|contact us name|"
    r"do you really want to logout|users have visited",
    re.IGNORECASE,
)
# Numbering artefacts between a list index and its question ("2", "Q3.").
_INDEX_LINE = re.compile(r"^(?:Q\s*)?\d{1,3}[.)]?$", re.IGNORECASE)
# Statutory section references - "16.", "17B.", "6A." - which look like sentence
# endings to a naive period count.
_SECTION_NUMBER = re.compile(r"\b\d{1,3}[A-Z]{0,2}\.\s")

# Prose chunking budget. Large enough to hold a full statutory sub-section,
# small enough that a hit points at something a reader can check quickly.
_CHUNK_CHARS = 1400


def _starts_mid_sentence(text: str) -> bool:
    """A chunk that begins part-way through a sentence cannot be quoted.

    Chunking a statute on block boundaries sometimes opens on a continuation -
    "[or the Insurance Scheme] to the credit of his account Insurance Fund], as
    the case may be." That is a real fragment of a real Act, correctly cited,
    and completely unreadable as an answer. Quoting it next to a clean sentence
    makes the good quote look less trustworthy, not the fragment more so.

    An opening capital letter or digit is a cheap, reliable proxy for "this is
    where a sentence starts".
    """
    head = text.lstrip()
    return bool(head) and not (head[0].isupper() or head[0].isdigit())


def _is_menu(text: str) -> bool:
    """Reject link menus that survived block-level filtering.

    Index pages concatenate into chunks that look substantial by length but say
    nothing - "Central Govt. Schemes and Policies Credit Guarantee Scheme...".

    The signal is **sentence terminators**, and only that. Measured over the real
    corpus: RBI and GSTN index strips carry 0 terminators per chunk, while the
    EPF Act's prose carries 4 to 81.

    One refinement is needed to make that signal honest: statutory section
    numbers ("16.", "17B.") are periods too, and a table of contents is nothing
    but section numbers. Counting them as sentence endings let the EPF Act's
    contents page - "16. Act not to apply to certain establishments 17B.
    Liability in case of transfer of 18. Protection of action taken in good
    faith" - score 26 terminators and sail through. They are stripped before
    counting, so the test measures sentences rather than enumeration.

    A word-repetition test was tried first and *rejected on the measurement*.
    The intuition - that menus repeat their labels while prose does not - is
    backwards for legal text: the EPF Act's densest passages score 0.33 unique
    words because statutes deliberately repeat their defined terms, while a
    Startup India link menu scores 0.72. Filtering on it removed 71 of 77
    statute chunks and kept the menus. The lesson is recorded here rather than
    quietly reverted, because it is the kind of plausible heuristic that would
    otherwise get proposed again.
    """
    words = text.split()
    if len(words) < 12:
        return True
    prose = _SECTION_NUMBER.sub(" ", text)
    return (prose.count(".") + prose.count("?")) < 2


_NAV_HINTS = (
    "skip to main content",
    "screen reader",
    "font size",
    "sitemap",
    "site map",
    "last updated",
    "copyright",
    "terms and conditions",
    "privacy policy",
    "hyperlinking policy",
    "view all",
    "click here",
    "read more",
    "login",
    "sign in",
)


def _is_noise(block: str) -> bool:
    """Navigation chrome, language switchers and bare labels."""
    if len(block) < 25:
        return True
    lowered = block.lower()
    if any(hint in lowered for hint in _NAV_HINTS):
        return True
    # Language switchers and menu strips: mostly non-Latin or mostly single
    # words with no sentence punctuation.
    letters = sum(c.isalpha() for c in block)
    ascii_letters = sum(c.isalpha() and c.isascii() for c in block)
    if letters and ascii_letters / letters < 0.5:
        return True
    return "." not in block and "?" not in block and len(block.split()) < 8


@dataclass(frozen=True)
class Block:
    text: str
    start: int
    end: int


def blocks(text: str) -> list[Block]:
    """Split into blocks, keeping character offsets into the source text."""
    out: list[Block] = []
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            start = offset + line.index(stripped) if stripped in line else offset
            out.append(Block(stripped, start, start + len(stripped)))
        offset += len(line) + 1
    return out


@dataclass(frozen=True)
class FaqPair:
    question: str
    answer: str
    start: int
    end: int


def parse_faq(text: str) -> list[FaqPair]:
    """Pair each question block with the answer blocks that follow it."""
    found: list[FaqPair] = []
    items = blocks(text)
    i = 0
    while i < len(items):
        block = items[i]
        is_question = block.text.endswith("?") and len(block.text) <= _MAX_QUESTION_CHARS
        if not is_question:
            i += 1
            continue

        answer_parts: list[str] = []
        j = i + 1
        end = block.end
        while j < len(items):
            nxt = items[j]
            if nxt.text.endswith("?") and len(nxt.text) <= _MAX_QUESTION_CHARS:
                break
            if _INDEX_LINE.match(nxt.text):
                # An index line immediately before the next question belongs to
                # that question, not to this answer.
                if j + 1 < len(items) and items[j + 1].text.endswith("?"):
                    break
                j += 1
                continue
            if _FOOTER.search(nxt.text):
                j += 1
                break
            answer_parts.append(nxt.text)
            end = nxt.end
            j += 1

        answer = " ".join(answer_parts).strip()[:_MAX_ANSWER_CHARS]
        if len(answer) >= _MIN_ANSWER_CHARS:
            found.append(FaqPair(block.text, answer, block.start, end))
        i = j if j > i else i + 1
    return found


def parse_indexed_faq(text: str) -> list[FaqPair]:
    """Pair Q&A in pages numbered row-by-row.

    The bare row number is the record separator. Within a record the question is
    every block up to and including the first one ending in a question mark -
    which is what reassembles a question the page wrapped across three lines -
    and the answer is everything after it.
    """
    items = blocks(text)
    starts = [i for i, b in enumerate(items) if _INDEX_LINE.match(b.text)]
    found: list[FaqPair] = []

    for n, start in enumerate(starts):
        stop = starts[n + 1] if n + 1 < len(starts) else len(items)
        record = items[start + 1 : stop]
        if not record:
            continue

        cut = next((i for i, b in enumerate(record) if b.text.endswith("?")), None)
        if cut is None:
            continue
        question = " ".join(b.text for b in record[: cut + 1]).strip()
        tail = record[cut + 1 :]
        stop = next((i for i, b in enumerate(tail) if _FOOTER.search(b.text)), len(tail))
        answer = " ".join(b.text for b in tail[:stop]).strip()[:_MAX_ANSWER_CHARS]
        if len(question) > _MAX_QUESTION_CHARS or len(answer) < _MIN_ANSWER_CHARS:
            continue
        found.append(FaqPair(question, answer, record[0].start, record[-1].end))
    return found


def chunk_prose(text: str, *, budget: int = _CHUNK_CHARS) -> list[Block]:
    """Chunk non-Q&A text on block boundaries, overlapping by one block."""
    items = [b for b in blocks(text) if not _is_noise(b.text)]
    chunks: list[Block] = []
    current: list[Block] = []
    size = 0
    for block in items:
        if current and size + len(block.text) > budget:
            chunks.append(
                Block(" ".join(b.text for b in current), current[0].start, current[-1].end)
            )
            current = current[-1:]  # one block of overlap
            size = len(current[0].text)
        current.append(block)
        size += len(block.text)
    if current:
        chunks.append(Block(" ".join(b.text for b in current), current[0].start, current[-1].end))
    return chunks


# A page is treated as an FAQ when pairing finds enough pairs to be a real Q&A
# document rather than a prose page containing a rhetorical question.
_FAQ_THRESHOLD = 5


def build_spans(
    entry: SourceEntry, result: FetchResult, *, fetched_at: datetime | None = None
) -> list[SourceSpan]:
    """Spans for one fetched source."""
    if not result.ok:
        return []
    when = fetched_at or result.fetched_at
    # Indexed first: it reassembles wrapped questions that the question-mark
    # parser would truncate. Fall back only when the page has no row numbering.
    pairs = parse_indexed_faq(result.text)
    if len(pairs) < _FAQ_THRESHOLD:
        pairs = parse_faq(result.text)

    def span_key(text: str) -> str:
        """Content-derived span id.

        Ordinal ids ("q24", "c3") were tried first and are a trap. They are
        positional, so dropping a single noisy span near the top of a page
        renumbers every span below it - which silently re-points every
        evaluation label at the wrong text. That failure is invisible: the eval
        keeps running and simply reports a retrieval regression that never
        happened. It was caught here only because the CI gate flagged a 12-point
        recall drop that turned out to be relabelling, not retrieval.

        Hashing the span's own text makes the id stable under parser changes and
        unstable exactly when the source text actually changes - which is the
        behaviour the freshness ledger wants anyway.
        """
        return hashlib.blake2b(text.encode("utf-8"), digest_size=4).hexdigest()

    def span(idx: str, text: str, citation: str, start: int, end: int) -> SourceSpan:
        return SourceSpan(
            span_id=f"{entry.id}:{idx}",
            source_id=entry.id,
            text=text,
            citation=citation,
            url=entry.url,
            publisher=entry.publisher,
            authority_tier=entry.authority_tier,
            domains=tuple(entry.domains),
            fetched_at=when,
            content_hash=result.content_hash,
            char_start=start,
            char_end=end,
            states=tuple(entry.states),
            entity_types=tuple(entry.entity_types),
        )

    if len(pairs) >= _FAQ_THRESHOLD:
        return [
            span(
                span_key(pair.question),
                f"{pair.question}\n{pair.answer}",
                f"{entry.title} - Q: {pair.question[:90]}",
                pair.start,
                pair.end,
            )
            for pair in pairs
        ]

    return [
        span(span_key(chunk.text), chunk.text, f"{entry.title} (part {n})", chunk.start, chunk.end)
        for n, chunk in enumerate(chunk_prose(result.text), start=1)
        if not _is_noise(chunk.text)
        and not _is_menu(chunk.text)
        and not _starts_mid_sentence(chunk.text)
    ]


def build_all(entries: list[SourceEntry], results: list[FetchResult]) -> list[SourceSpan]:
    """Spans for every source, deduplicated.

    Because ids are content hashes, an exact duplicate collides by construction
    - which is the right outcome: several of these pages repeat an FAQ entry
    verbatim in two sections, and indexing it twice would let one answer occupy
    two of the four citation slots and inflate its BM25 document frequency.
    """
    by_id = {r.source_id: r for r in results}
    seen: set[str] = set()
    spans: list[SourceSpan] = []
    for entry in entries:
        result = by_id.get(entry.id)
        if result is None:
            continue
        for span in build_spans(entry, result):
            if span.span_id in seen:
                continue
            seen.add(span.span_id)
            spans.append(span)
    return spans


def domain_counts(spans: list[SourceSpan]) -> dict[Domain, int]:
    counts: dict[Domain, int] = {}
    for span_ in spans:
        for domain in span_.domains:
            counts[domain] = counts.get(domain, 0) + 1
    return counts
