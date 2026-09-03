"""The pipeline. Four outcomes, and only one of them is an answer.

The ordering below is the design. Checks that can rule out an answer run
*before* retrieval, because retrieving first invites answering a question that
should not have been answered at all - a plausible span is always available, and
once one is on screen the temptation is to use it.

1. **Judgement?** "Should I register an LLP or a Pvt Ltd" has no answer in any
   source, because it is not a question about what a rule says. Return the
   factors and the sources; never a recommendation.
2. **State known?** If the topic is state law and the state is unknown, ask.
   Answering all-India here would be the most common way to be wrong.
3. **Retrieve, filtered by applicability**, then rerank.
4. **Grounded enough?** Below the score floor, refuse and say what was searched.

The default answerer is **extractive**: a claim's text is the source's own words,
and the span it quotes is its support. That makes fabrication structurally
impossible rather than merely unlikely - there is no generation step in which a
sentence could acquire a fact the corpus does not contain. The optional model
layer (``agent.llm``) only rewrites what has already been retrieved and cited.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent.retrieval.rerank import IdentityReranker, Reranker
from agent.retrieval.store import ScoredSpan, SpanStore
from agent.router import Routing, route
from agent.schema import Answer, AnswerKind, CitedSpan, Claim, EntityType, SourceSpan
from sources.loader import Allowlist

# The refusal gate is *query coverage*, not the hybrid score.
#
# This is worth stating plainly because the obvious choice is wrong. ``score`` is
# min-max normalised across the candidate set, so the top hit is always ~1.0 no
# matter how irrelevant it is - gating on it can never refuse anything. Measured
# on this corpus: "how do I train a neural network" retrieves a top span with
# score 0.96, and "who won the cricket world cup" one with 0.83.
#
# Raw BM25 was the next candidate and also fails: it ran 8.5 for an out-of-scope
# capital-gains question against 6.9 for an in-scope incorporation question,
# because BM25 rewards a rare term matching anywhere. It is retained on the hit
# for diagnostics but is not the gate.
#
# IDF-weighted query coverage - the share of the question's *information* the
# span contains - does separate them, and the threshold is swept against the
# evaluation set rather than chosen by eye (`python -m eval.runner --sweep`).
#
# The sweep shows overall routing accuracy peaking at 0.846 across a plateau
# from 0.22 to 0.28, and the choice within that plateau is a judgement about
# which error is worse:
#
#     threshold   grounded   refused   over-refusal
#         0.22      0.976     0.250       0.024
#         0.28      0.878     0.583       0.122
#
# 0.28 is chosen. Both ends score the same overall, but at 0.22 the system
# answers three-quarters of the questions it should refuse - and *these* are the
# dangerous ones, because an unanswerable incorporation question still retrieves
# a confident, correctly-cited GST span. A wrong refusal costs the founder a
# rephrase; a wrong answer about a filing deadline costs them a penalty.
MIN_COVERAGE = 0.28

# Retrieve wide, answer narrow. A reranker can only reorder what the first stage
# returned, so the candidate pool is its ceiling.
CANDIDATE_K = 20
ANSWER_K = 4


def _answer_text(span: SourceSpan) -> str:
    """The assertion part of a span.

    FAQ spans are stored as "question\\nanswer" so that retrieval can match on
    the question's wording, which is how a person phrases the query. What gets
    quoted back, though, is the answer - restating the question as if it were a
    finding would be padding.
    """
    _, _, tail = span.text.partition("\n")
    return (tail or span.text).strip()


class Answerer:
    def __init__(
        self,
        store: SpanStore,
        allowlist: Allowlist,
        *,
        reranker: Reranker | None = None,
        candidate_k: int = CANDIDATE_K,
        answer_k: int = ANSWER_K,
        min_coverage: float = MIN_COVERAGE,
    ) -> None:
        self.store = store
        self.allowlist = allowlist
        self.reranker = reranker or IdentityReranker()
        self.candidate_k = candidate_k
        self.answer_k = answer_k
        self.min_coverage = min_coverage

    # -- helpers ---------------------------------------------------------

    def _searched(self) -> tuple[str, ...]:
        """What a refusal must be able to name."""
        return tuple(f"{e.publisher} - {e.title}" for e in self.allowlist.fetchable())

    def _cite(self, hit: ScoredSpan, now: datetime) -> CitedSpan:
        entry = self.allowlist.get(hit.span.source_id)
        return CitedSpan.of(
            hit.span, status=hit.span.status(refresh_days=entry.refresh_days, now=now)
        )

    def candidates(self, question: str, routing: Routing) -> list[ScoredSpan]:
        """First-stage retrieval, before any reranking."""
        state = routing.applicability.state
        entity = routing.applicability.entity_type

        def applicable(span: SourceSpan) -> bool:
            return span.applies_to(state=state, entity=entity)

        return self.store.search(question, k=self.candidate_k, where=applicable)

    def retrieve(self, question: str, routing: Routing) -> list[ScoredSpan]:
        return self.reranker.rerank(question, self.candidates(question, routing), k=self.answer_k)

    # A span is only worth quoting alongside the best one if it is comparably
    # relevant. Without this the answer to "can an OPC get Startup India
    # benefits" led with the correct sentence and then appended three unrelated
    # FAQ entries - including the definition of a term sheet - because each
    # cleared the absolute floor on its own. More citations is not more rigour;
    # it is the reader having to work out which one answered the question.
    RELATIVE_FLOOR = 0.8

    def _select(self, candidates: list[ScoredSpan], ranked: list[ScoredSpan]) -> list[ScoredSpan]:
        """Decide *whether* to answer from the candidates; decide *what to quote* from the ranking.

        These are two different questions and coupling them was a measured
        mistake. When the gate ran on the reranked top-k, adding the
        cross-encoder improved retrieval (recall@1 0.610 -> 0.707) while making
        routing worse (0.862 -> 0.815, over-refusal 0.122 -> 0.195): the
        reranker promotes spans that are semantically apt but share fewer words
        with the question, so they cleared the ranking and then failed the
        lexical gate, and answerable questions came back refused.

        "Can this corpus answer the question at all" is a property of what was
        retrieved, not of the order it ended up in - so the gate reads the whole
        candidate pool, and the reranker only chooses what to quote.
        """
        if not candidates:
            return []
        # Gate on the first-stage top-k, not the whole candidate pool. The pool
        # is 20 spans deep to give the reranker room, and somewhere in 20 spans
        # there is nearly always one sharing enough vocabulary to clear the
        # threshold - gating on the pool let "how do I train a neural network"
        # through. The first-stage ordering is by hybrid score, so this is still
        # independent of which reranker is installed.
        gate_pool = candidates[: self.answer_k]
        best = max(h.query_coverage for h in gate_pool)
        if best < self.min_coverage:
            return []

        chosen = [h for h in ranked if h.query_coverage >= self.RELATIVE_FLOOR * best]
        if chosen:
            return chosen
        # The gate has already decided this question is answerable, so the
        # selection must yield something. A reranker can promote spans that are
        # semantically apt but lexically sparse, leaving nothing above the
        # relative floor; refusing at that point would turn a *ranking* choice
        # back into a *routing* choice, which is the coupling this method exists
        # to break. Fall back to the best-covered candidate.
        return [max(gate_pool, key=lambda h: h.query_coverage)]

    # -- the pipeline ----------------------------------------------------

    def answer(
        self,
        question: str,
        *,
        state: str | None = None,
        entity: EntityType | None = None,
        now: datetime | None = None,
    ) -> Answer:
        moment = now or datetime.now(UTC)
        routing = route(question, state=state, entity=entity)

        if routing.is_judgement:
            return self._informational(question, routing, moment)
        if routing.missing_state:
            return Answer(
                kind=AnswerKind.CLARIFY,
                question=question,
                applies_to=routing.applicability,
                clarifying_question=routing.clarifying_question(),
                as_of=moment,
            )

        candidates = self.candidates(question, routing)
        ranked = self.reranker.rerank(question, candidates, k=self.answer_k)
        strong = self._select(candidates, ranked)
        if not strong:
            return Answer(
                kind=AnswerKind.REFUSED,
                question=question,
                applies_to=routing.applicability,
                searched=self._searched(),
                as_of=moment,
            )

        cited = [self._cite(h, moment) for h in strong]
        return Answer(
            kind=AnswerKind.GROUNDED,
            question=question,
            applies_to=routing.applicability,
            claims=tuple(
                Claim(text=_answer_text(h.span), supported_by=(h.span.span_id,)) for h in strong
            ),
            cited_spans=tuple(cited),
            as_of=moment,
        )

    def _informational(self, question: str, routing: Routing, moment: datetime) -> Answer:
        """Factors and sources for a question that asks for judgement.

        The considerations are drawn from what the retrieved sources actually
        address, not from an opinion about which option is better. That
        distinction is the whole point: naming what a decision turns on is
        information; naming which way to decide it would be advice this project
        is not in a position to give.
        """
        hits = self.retrieve(question, routing)
        considerations = [
            "Choosing between entity structures turns on facts this tool does not have - "
            "funding plans, number of owners, compliance appetite and cost tolerance among them. "
            "A chartered accountant or company secretary should make this call with you.",
        ]
        considerations += [
            f"The official sources do address: {h.span.text.partition(chr(10))[0].rstrip('?')}"
            for h in hits[:3]
        ]
        return Answer(
            kind=AnswerKind.INFORMATIONAL_ONLY,
            question=question,
            applies_to=routing.applicability,
            considerations=tuple(considerations),
            cited_spans=tuple(self._cite(h, moment) for h in hits[:3]),
            as_of=moment,
        )


def build_answerer(reranker: Reranker | None = None) -> Answerer:
    """Assemble from the built corpus on disk."""
    from agent.retrieval.store import build_store
    from ingest.build_corpus import load_spans
    from sources.loader import load_allowlist

    spans = load_spans()
    if not spans:
        raise RuntimeError("no corpus on disk - run: python -m ingest.build_corpus")
    return Answerer(build_store(spans), load_allowlist(), reranker=reranker)
