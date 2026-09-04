# Retrieval

*How a question finds a span, and how the system decides it cannot answer.*

[← back to the README](../README.md)

---

## Retrieval

Hybrid BM25 + vector over an in-memory matrix, then optional cross-encoder
reranking.

**Why hybrid is not a refinement here.** Compliance questions turn on exact
tokens — a form number (`INC-20A`), a section reference (`Section 2(6)`), a
threshold (`20 lakh`). A dense embedding blurs precisely those. Conversely BM25
cannot see that "do I need to register" and "is registration required" are the
same question. Each half covers the other's failure.

**Why there is no vector database.** Measured on this corpus:

| | |
|---|---|
| spans | 541 |
| vector matrix | 1.1 MB at 512 dims |
| index build | 0.31 s |
| exact search, p50 / p95 | **0.38 ms / 0.49 ms** |

A round trip to any hosted vector store is 20–50 ms of network before it does
any work, and an HNSW index would be approximate where this is exact. It would
cost money and latency for worse recall.

### Does the embedding model earn its place?

The semantic half of retrieval can be character n-gram hashing (free, offline,
semantically blind) or a real embedding model — `BAAI/bge-small-en-v1.5`, local,
needing no new dependency because `sentence-transformers` is already installed
for the cross-encoder. `python -m eval.runner --compare-embedder`, 87 questions:

| | recall@1 | recall@5 | MRR | routing | added startup |
|---|---|---|---|---|---|
| hashing + no reranker | 0.596 | 0.830 | 0.698 | 0.713 | — |
| model + no reranker | **0.681** | 0.894 | 0.760 | 0.678 | +5.7 s |
| hashing + cross-encoder | 0.681 | 0.894 | 0.764 | **0.885** | +7.9 s |
| **model + cross-encoder** | 0.681 | **0.936** | **0.780** | **0.885** | +13.6 s |

**The interesting result is the row that does not move.** On its own the model is
a large win — recall@1 0.596 → 0.681, and it bridges paraphrases hashing cannot
("how long can my staff work in a day" against "what are the working hours for
employees"). But once the cross-encoder is in front of it, recall@1 is *identical*
either way: the cross-encoder was already recovering what the weak embedder
missed, because BM25 got the right span into the 20-candidate pool often enough
for reranking to find it. What remains is recall@5 +0.042 and MRR +0.016, with
routing accuracy unchanged to three decimals.

So it ships as the default when installed — there is no regression and 0.936 is
the best measured recall@5 — but it is a much smaller win than it looks like in
isolation, and it costs about six seconds of startup. `--embedder hashing` turns
it off. This is the same test the reranker had to pass; the reranker passed it
more convincingly.

There is still no generative model anywhere. This changes which spans are
*found*, never what is said about them.

### Fixing the refusal gate

The gate originally measured IDF-weighted vocabulary overlap, and a rephrasing
could defeat it: *"How much does it cost to register a trademark for a logo in
India?"* refused correctly while *"how much does it cost to trademark a logo in
India"* returned a definition of a term sheet — a real quote, correctly cited,
and no answer to the question.

Two things were needed to fix it, and the first mattered more.

**The refusal set was too easy.** Twelve mostly-obvious out-of-scope questions
scored 0.667, which flattered the gate. Adding fourteen adversarial cases — every
rephrasing known to defeat it, plus in-scope-but-uncovered questions like AOC-4
penalties and minimum paid-up capital — put the true number at **0.385**. The
first result of the work was the metric getting worse, because it started being
honest.

**Then: no lexical signal fixes it.** Raw BM25, a discriminative-term match, and
a joint grid search over three parameters were all measured. The best lexical
rule scored 0.714 overall against the incumbent's 0.686, and bought it by
trading answering ability away (grounded 0.864 → 0.705). That is not a fix; it
is moving the failure. Vocabulary overlap and topical relevance are different
quantities, and no threshold on the first recovers the second.

**A cross-encoder does fix it, because it measures the right thing.** It scores
the question and the span jointly, producing an absolute answer to "is this span
about what was asked":

| gate | grounded | refused | over-refusal | overall |
|---|---|---|---|---|
| coverage (lexical) | 0.864 | 0.385 | 0.136 | 0.732 |
| **cross-encoder @ 0.05** | **0.977** | **0.654** | **0.023** | **0.878** |

It improves *both* directions at once, which is what distinguishes a fix from a
threshold move. The score costs nothing extra — it is the reranker's own output,
already computed for ordering — so when the extra is installed, better refusals
are free.

### Does the cross-encoder earn its place?

`python -m eval.runner --compare-rerank`, same 82 questions:

| | recall@1 | recall@5 | MRR | latency |
|---|---|---|---|---|
| hybrid only | 0.636 | 0.864 | 0.734 | 0.38 ms |
| + cross-encoder | **0.727** | **0.932** | **0.805** | 665 ms |

`BAAI/bge-reranker-base`, CPU. It buys about 9 points of recall@1 for roughly
1,750× the retrieval latency, plus a 2 GB dependency and a 13-second model load.

On ranking alone that trade would be arguable. It is not arguable once the same
score is doing the refusal gating above, which is why **the cross-encoder is now
the default when installed** and the CLI prints a warning when it is not. It
stays an optional extra because 2 GB is a real imposition for someone who only
wants to read the code — but an install without it is a measurably weaker
system, and the README, the CLI and the second CI baseline all say so rather
than letting the difference pass unnoticed.

Getting this comparison to be *meaningful* required a fix worth describing. When
the refusal gate read the reranked list while still scoring it lexically, the
cross-encoder improved retrieval and made routing **worse**: it promotes spans
that are semantically apt but share fewer words with the question, so they won
the ranking and then failed a lexical gate. Retrieval quality and answerability
are separate questions, and the gate had been reading the ranking as if it
answered both. Once separated, the reranker's score could be used for what it is
actually good at — which is how it ended up being the refusal gate.

---

---

[← back to the README](../README.md)
