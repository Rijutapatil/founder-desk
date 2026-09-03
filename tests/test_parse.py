"""Parsing government pages into quotable spans."""

from __future__ import annotations

from ingest.fetch import FetchResult, content_hash, extract_text, normalise
from ingest.parse import build_spans, parse_faq, parse_indexed_faq
from tests.conftest import NOW

INDEXED = """Question
Answer
1
Does aggregate turnover include value of inward supplies received on which RCM is
payable?
Refer Section 2(6) of CGST Act. Aggregate turnover does not include value of inward
supplies on which tax is payable on reverse charge basis.
2
What if the dealer migrated with wrong PAN as the status of firm was changed from
proprietorship to partnership?
New registration would be required as partnership firm would have new PAN.
"""

PLAIN = """What is the Universal Account Number?
It is a unique number allotted to every provident fund member by the organisation.
How can I know the balance in my PF account?
You may check the balance through the member portal or the missed call facility.
"""


class TestIndexedFaq:
    """The layout used by CBIC: a numbered table whose cells wrap across lines."""

    def test_wrapped_question_is_reassembled(self) -> None:
        pairs = parse_indexed_faq(INDEXED)
        assert pairs[0].question.startswith("Does aggregate turnover include")
        assert pairs[0].question.endswith("payable?")

    def test_answer_does_not_bleed_into_the_next_question(self) -> None:
        pairs = parse_indexed_faq(INDEXED)
        assert "What if the dealer migrated" not in pairs[0].answer
        assert pairs[0].answer.startswith("Refer Section 2(6)")

    def test_both_records_are_found(self) -> None:
        assert len(parse_indexed_faq(INDEXED)) == 2


class TestPlainFaq:
    def test_question_mark_pairing(self) -> None:
        pairs = parse_faq(PLAIN)
        assert len(pairs) == 2
        assert pairs[0].question == "What is the Universal Account Number?"
        assert "unique number" in pairs[0].answer


def test_footer_is_not_absorbed_into_the_final_answer() -> None:
    """The last Q&A on a page has no next question to stop at.

    Observed for real: the Startup India FAQ's final answer ran to thousands of
    characters of cookie notice, password rules and visitor counter.
    """
    page = PLAIN + "\n".join(
        [
            "Terms of Use Privacy Policy Site map",
            "1,09,81,843 users have visited the portal since inception",
            "Your password must contain atleast: 8 to 15 characters in length",
        ]
    )
    last = parse_faq(page)[-1]
    assert "password must contain" not in last.answer
    assert "users have visited" not in last.answer


def test_link_menus_are_dropped_from_prose_chunks() -> None:
    menu = "\n".join(
        ["Central Govt Schemes and Policies Credit Guarantee Scheme Fund of Funds"] * 6
    )
    spans = build_spans(
        _entry(), FetchResult("src", "u", 200, NOW, menu, content_hash(menu), False)
    )
    assert spans == []


def test_prose_chunks_survive() -> None:
    prose = " ".join(
        [
            "Every employer shall register the establishment within thirty days of becoming liable.",
            "The contribution payable by the employer is twelve percent of the basic wages.",
            "An employee may contribute a higher amount at their own option, without obliging the employer to match it.",
        ]
    )
    spans = build_spans(
        _entry(), FetchResult("src", "u", 200, NOW, prose, content_hash(prose), False)
    )
    assert spans and "twelve percent" in spans[0].text


def test_span_ids_are_content_derived_not_positional() -> None:
    """Guards the bug that silently re-pointed every evaluation label.

    Dropping one span used to renumber every span after it. Ids are hashes of
    the span's own text, so an unrelated span disappearing must leave the others
    untouched.
    """
    records = [
        f"{n}\nIs question number {n} answered here?\nYes, this is the answer to question {n} "
        f"and it is long enough to clear the minimum answer length."
        for n in range(1, 8)
    ]
    page = "Question\nAnswer\n" + "\n".join(records)
    full = build_spans(_entry(), FetchResult("src", "u", 200, NOW, page, "h", False))
    assert len(full) == 7, "should parse as an indexed FAQ, not prose"

    # Drop the *first* record. Under positional ids every remaining span would
    # shift by one; under content ids they must be untouched.
    without_first = "Question\nAnswer\n" + "\n".join(records[1:])
    trimmed = build_spans(_entry(), FetchResult("src", "u", 200, NOW, without_first, "h", False))
    assert [s.span_id for s in trimmed] == [s.span_id for s in full[1:]]


def test_normalisation_ignores_markup_churn() -> None:
    assert content_hash("a   b\n\nc") == content_hash("a b c")


def test_extract_text_keeps_block_structure() -> None:
    text = extract_text("<div><p>Question?</p><p>Answer.</p><script>x=1</script></div>")
    assert text.splitlines() == ["Question?", "Answer."]
    assert "x=1" not in text


def test_normalise_collapses_whitespace() -> None:
    assert normalise("  a \t b\n c ") == "a b c"


def _entry():
    from agent.schema import AuthorityTier, Domain
    from sources.loader import SourceEntry

    return SourceEntry(
        id="src",
        publisher="CBIC",
        title="Test source",
        url="https://cbic-gst.gov.in/faq.html",
        authority_tier=AuthorityTier.GUIDANCE,
        license="GODL-India",
        refresh_days=90,
        domains=(Domain.GST,),
    )
