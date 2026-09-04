"""`founder-desk ask` - the command-line interface.

Output is shaped by one rule: **the source's own words are the answer, and the
provenance travels with them.** Every quote is printed under the citation,
publisher, authority tier and the date the text was fetched, because a
compliance answer without a date is not checkable.
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from agent.answerer import Answerer, build_answerer
from agent.retrieval.embedder import load_embedder
from agent.retrieval.rerank import load_reranker
from agent.schema import Answer, AnswerKind, AuthorityTier, EntityType, SpanStatus

_TIER_LABEL = {
    AuthorityTier.STATUTE: "statute",
    AuthorityTier.INSTRUMENT: "notification/direction",
    AuthorityTier.GUIDANCE: "official guidance",
    AuthorityTier.EXTERNAL: "NOT A GOVERNMENT SOURCE",
}


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(text, width=94, initial_indent=indent, subsequent_indent=indent)


def render(answer: Answer) -> str:
    out: list[str] = ["", f"Q: {answer.question}", f"   [{answer.applies_to.describe()}]", ""]

    if answer.kind is AnswerKind.CLARIFY:
        out += [_wrap(answer.clarifying_question or ""), ""]
    elif answer.kind is AnswerKind.REFUSED:
        out += [
            _wrap(
                "I cannot ground an answer to this in the allowlisted sources, so I am not "
                "going to guess. This is either outside what this tool covers, or in a domain "
                "whose sources could not be collected - see the coverage table in the README."
            ),
            "",
            f"  searched {len(answer.searched)} official sources:",
        ]
        out += [f"    - {s}" for s in answer.searched]
        out.append("")
    elif answer.kind is AnswerKind.INFORMATIONAL_ONLY:
        out.append("  This asks for a judgement no published source can make for you.\n")
        out += [_wrap(f"- {c}") for c in answer.considerations]
        out.append("")
    else:
        for claim in answer.claims:
            out += [_wrap(claim.text), ""]

    if answer.cited_spans:
        out.append("  sources")
        for span in answer.cited_spans:
            flag = "" if span.status is SpanStatus.CURRENT else f"  [{span.status.value.upper()}]"
            out.append(
                f"    {span.citation[:88]}{flag}\n"
                f"      {span.publisher} · {_TIER_LABEL[span.authority_tier]} · "
                f"fetched {span.fetched_at:%Y-%m-%d}\n"
                f"      {span.url}"
            )
        out.append("")

    if answer.external_sources:
        publishers = sorted({s.publisher for s in answer.external_sources})
        out += [
            _wrap(
                "Part of this answer is quoted from a source that is not a government "
                "publication: " + "; ".join(publishers) + ". It is included because the "
                "government publishes nothing on this subject that can be collected. "
                "Treat it as one step further from the law than the rest.",
                indent="  ! ",
            ),
            "",
        ]

    if answer.has_stale_citation:
        out += [
            _wrap(
                "One or more sources above are past their refresh window. Confirm against the "
                "live page before relying on this.",
                indent="  ! ",
            ),
            "",
        ]

    out += [_wrap(answer.disclaimer, indent="  "), ""]
    return "\n".join(out)


def run_chat(answerer: Answerer, *, state: str | None, entity: str | None) -> int:
    """A session at the terminal.

    The reason this exists rather than repeated `ask` calls: a clarifying
    question is unanswerable in a one-shot interface. "Which state is the
    registered office in?" has nowhere to put the reply, so the founder has to
    retype the whole question with --state. Here the next line answers it.
    """
    from agent.conversation import Conversation

    conversation = Conversation(
        answerer, state=state, entity=EntityType(entity) if entity else None
    )
    print("\n  founder-desk — type a question, or 'reset' to forget what you have told me.")
    print("  Ctrl-D to leave.\n")

    while True:
        try:
            message = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not message:
            continue
        if message.lower() in {"reset", "forget"}:
            conversation.reset()
            print("  (forgotten)\n")
            continue

        turn = conversation.ask(message)
        if turn.resolved_from_pending:
            print(f"  answering: {turn.question}")
        print(render(turn.answer))
        if conversation.known != "nothing established yet":
            print(f"  remembering — {conversation.known}\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="founder-desk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="ask a compliance question")
    ask.add_argument("question")
    ask.add_argument("--state", help="ISO 3166-2:IN code, e.g. MH, KA, DL")
    ask.add_argument("--entity", choices=[e.value for e in EntityType])
    ask.add_argument("--reranker", default="auto", choices=("auto", "identity", "cross-encoder"))
    ask.add_argument(
        "--embedder",
        default="auto",
        choices=("auto", "hashing", "model"),
        help="hashing starts ~6s faster; the model gains recall@5 (see README)",
    )

    chat = sub.add_parser("chat", help="a session: clarifying questions can be answered")
    chat.add_argument("--state", help="ISO 3166-2:IN code, e.g. MH")
    chat.add_argument("--entity", choices=[e.value for e in EntityType])
    chat.add_argument("--reranker", default="auto", choices=("auto", "identity", "cross-encoder"))
    chat.add_argument("--embedder", default="auto", choices=("auto", "hashing", "model"))

    sub.add_parser("sources", help="list the allowlisted sources")

    args = parser.parse_args()

    if args.command == "sources":
        from sources.loader import load_allowlist

        allowlist = load_allowlist()
        for entry in allowlist.entries:
            status = "" if entry.fetch_status.value == "ok" else f"  [{entry.fetch_status.value}]"
            print(f"  tier {entry.authority_tier}  {entry.id:<32} {entry.publisher}{status}")
        print(f"\n{len(allowlist)} sources, {len(allowlist.blocked())} not collectable")
        return 0

    try:
        answerer = build_answerer(load_reranker(args.reranker), load_embedder(args.embedder))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "chat":
        return run_chat(answerer, state=args.state, entity=args.entity)

    if not answerer.reranker.name.startswith("cross-encoder"):
        # Not a nag: without the cross-encoder the refusal gate falls back to a
        # lexical signal that is measurably worse at knowing what it does not
        # know (0.385 against 0.692), and in a compliance tool that is the
        # difference that matters most.
        print(
            "  note: running with the lexical refusal gate. The cross-encoder gate refuses "
            'far more reliably - install it with: pip install -e ".[rerank]"',
            file=sys.stderr,
        )

    answer = answerer.answer(
        args.question,
        state=args.state,
        entity=EntityType(args.entity) if args.entity else None,
    )
    print(render(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
