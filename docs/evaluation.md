# Evaluation

*What is measured, what the numbers mean, and what the CI gate enforces.*

[← back to the README](../README.md)

---

## Evaluation criteria

What "working" means, and what each number is accountable for. All of it runs on
94 questions in [`eval/questions.yaml`](eval/questions.yaml) at `$0.0000`.

| Criterion | Measures | Gate |
|---|---|---|
| **recall@1 / recall@5** | Is the right span retrieved at all? The ceiling on everything after it | 0.02 absolute, downward |
| **MRR** | Where it lands — catches quality sliding from rank 1 to rank 5 | 0.02 absolute, downward |
| **Routing accuracy** | Did it pick the right *kind* of response, not just a good span | 0.02 absolute, downward |
| **Refusal accuracy** | Does it decline what the corpus cannot answer | 0.02 absolute, downward |
| **Over-refusal** | Answerable questions wrongly refused | 0.05, **upward** |
| **Fabricated citations** | Authority that was never retrieved | **zero tolerance** |
| **Unofficial citations** | A source not on the allowlist | **zero tolerance** |
| **External citation rate** | Reliance on declared tier-4 sources | 0.02, **upward** |
| **Citation faithfulness** | Catches a corpus rotting in place while retrieval looks fine | 0.02 absolute, downward |
| **Cost per answer** | Buying accuracy with spend should be a decision | 25% ratio |

Three of these are deliberately inverted, and each guards a way of gaming the
rest: refuse everything and refusal accuracy hits 1.000; lean on easier
non-government sources and coverage looks better; let the corpus go stale and
retrieval numbers never move while every citation quietly stops being vouched
for.

**Reading the set honestly.** 94 questions is small — three misses move
recall@5 by a point. The refusal half is deliberately adversarial: 14 of the 27
are rephrasings that defeated an earlier gate, or questions inside a covered
topic the corpus does not answer. Every answerable question is a hand-written
paraphrase, never the source's own wording, and a test enforces that.

## Evaluation

94 questions in [`eval/questions.yaml`](eval/questions.yaml): 55 answerable, 27
that must be refused, 7 that must ask for a state, 5 that must decline to
recommend.

The refusal half is deliberately adversarial. Fourteen of the twenty-six are
rephrasings that defeated an earlier version of the gate, or questions inside a
covered topic that the corpus does not actually answer. A refusal set of obvious
nonsense measures nothing.

Every answerable question is a **paraphrase**, never the source's own wording.
The corpus is built from FAQ pages, so the lazy version — copy each source
question and label it with its own span — would measure string matching and
report near 1.00. A test enforces this ([`test_questions_are_paraphrases_not_copies`](tests/test_eval_dataset.py)),
and it caught one verbatim question in this very file.

Gold labels reference **a phrase from the source question**, not a span id, and
resolve at load time. Ambiguous or missing anchors are a hard error.

### Results

Two systems are measured and both baselines are committed, because the project
ships two refusal gates. `$0.0000` per answer either way — neither calls an API.

| | lexical gate | **cross-encoder gate** (default when installed) |
|---|---|---|
| recall@1 (n=55) | {f['retrieval']['recall@1']:.3f} | **{d['retrieval']['recall@1']:.3f}** |
| recall@5 | {f['retrieval']['recall@5']:.3f} | **{d['retrieval']['recall@5']:.3f}** |
| MRR | {f['retrieval']['mrr']:.3f} | **{d['retrieval']['mrr']:.3f}** |
| routing overall (n=94) | {f['routing']['overall']:.3f} | **{d['routing']['overall']:.3f}** |
| refused | {f['routing']['refused']:.3f} | **{d['routing']['refused']:.3f}** |
| over-refusal | {f['routing']['over_refusal']:.3f} | **{d['routing']['over_refusal']:.3f}** |

| citation faithfulness | |
|---|---|
| faithful | 1.000 |
| **fabricated** | **0.000** |
| **unofficial** | **0.000** |

Fabrication is zero *by construction*, not by luck: the default answerer is
extractive, so a claim's text is the source's own words and there is no
generation step in which a sentence could acquire a fact the corpus does not
contain. The check exists anyway, because it must still hold the day a
model-backed answerer is added — a gate written after the risk appears is a gate
written too late.

### Reading these numbers honestly

- **87 questions is small.** Recall@5 of 0.894 means five misses. Treat the
  third decimal as noise.
- **Refusal accuracy is 0.679, still the weakest number here**, and it is
  reported next to over-refusal on purpose: refusing everything would score
  1.000 on one and destroy the other. The nine questions wrongly answered are
  almost all in-scope-but-uncovered — board size, paid-up capital, name
  reservation — where the retrieved span is genuinely relevant and simply does
  not contain the answer.
- **Routing accuracy is not answer correctness.** It measures whether the system
  chose the right *kind* of response and retrieved the right span — not whether
  a reader would be well served by the quote.
- **The corpus is 94% tier-3 guidance.** These numbers describe finding the
  right FAQ entry, which is a lower bar than reading the Act.

### Both thresholds were swept, not chosen

`python -m eval.runner --sweep`. Overall accuracy peaks at 0.846 across a plateau
from 0.22 to 0.28, and the choice within it is a judgement about which error is
worse:

| threshold | grounded | refused | over-refusal |
|---|---|---|---|
| 0.22 | 0.976 | 0.250 | 0.024 |
| **0.28** | 0.878 | **0.583** | 0.122 |

0.28 is chosen: at 0.22 the system answers three-quarters of what it should
refuse, and those are the dangerous ones. A wrong refusal costs a rephrase; a
wrong answer about a filing deadline costs a penalty.

### Three measurements that overturned the obvious approach

**The normalised score cannot refuse anything.** Min-max normalising hybrid
scores makes the top hit ~1.0 regardless of quality — "how do I train a neural
network" retrieved a span scoring 0.96. Raw BM25 was the next candidate and also
fails: 8.5 for an off-topic capital-gains question against 6.9 for an in-scope
incorporation one. The gate is IDF-weighted query coverage instead, and the two
rejected signals are kept on every hit for diagnostics.

**A state you collect but cannot use is worse than not asking.** Shops &
Establishments, professional tax and stamp duty are state law, and the router
correctly asked "which state is the registered office in?". But **zero of 499
spans carried a state scope**, so the answer that followed came from a central
Act and was stamped `state: MH` — advertising a jurisdiction that had played no
part in it. The state was collected, ignored, and then displayed.

The fix has three parts. Delhi Shops & Establishments is now in the corpus as the
first state-scoped source (30 spans), so the question can pay off. A state-law
answer must now be *carried by a state-scoped span* — quoting central law and
labelling it with a state is refused. And the corpus is asked before the founder
is: with no coverage for a state, it refuses immediately and names the gap
(*"state-specific sources held: DL — nothing for MH"*) rather than spending a
turn on a fact it cannot use.

Scoping is also what makes these sources safe where the NSWS pages were not: a
span scoped to a state is invisible to every question that is not about that
state, so it cannot leak.

One more thing was needed to make it work. 30 Delhi spans against 529 is
arithmetic, not relevance: a single ranked search filled its whole candidate list
with GST text and the Delhi Act never reached the reranker. Retrieval is now
stratified by jurisdiction — a covered state's own spans are retrieved as their
own stratum, effectively all of them, and the cross-encoder chooses from the
union. That lifted routing 0.874 → 0.885 and halved over-refusal.

**Shallow coverage of a domain is worse than none.** Incorporation had one span,
so the obvious next move was more incorporation sources. Driving the NSWS filter
UI produced the full Ministry of Corporate Affairs and Ministry of Labour
approval catalogues — including the INC-20A declaration and DIN, both named in
this README as refusals. Adding all nine made the system measurably worse:

| | overall | refused | recall@1 |
|---|---|---|---|
| without them | **0.878** | **0.654** | **0.727** |
| with all nine | 0.793 | 0.423 | 0.705 |

Each page is a one-paragraph description of what an approval *is* — not when it
is due, what it costs, or how many directors it needs. That makes them topically
close to a wide class of company questions the corpus still cannot answer, so the
relevance gate admits them and an honest refusal becomes a plausible error:
*"what is the minimum paid up capital for a private limited company"* came back
with the text of the INC-20A declaration. Excluding only the five marginal pages
changed nothing (0.793 / 0.423), so the harm is the shape they all share, not the
edge cases. They stay in `sources.yaml` with `fetch_status: excluded` and the
numbers attached — a recorded result rather than a deleted branch, and distinct
from the sources that simply cannot be fetched.

**No lexical signal can gate refusals well.** Documented in full above: the best
of raw BM25, discriminative-term matching and a three-parameter grid search
reached 0.714 overall against an incumbent 0.686, and only by trading answering
ability for refusals. The failure is not a badly-chosen threshold, it is the
signal — vocabulary overlap is not topical relevance.

**Word-repetition does not identify navigation chrome.** The intuition — menus
repeat their labels, prose does not — is backwards for legal text. The EPF Act's
densest passages score 0.33 unique words because statutes repeat defined terms;
a Startup India link menu scores 0.72. Filtering on it removed 71 of 77 statute
chunks and kept the menus. Sentence-terminator count separates them cleanly
(menus: 0, statute prose: 4–81) and is what ships — with one correction, since
statutory section numbers ("16.", "17B.") are periods too, and a table of
contents is nothing but section numbers. Stripping them before counting is what
stops the EPF Act's contents page scoring 26 "sentences".

---

## The CI gate

`python -m eval.gate_cli` compares a fresh run to a committed baseline and exits
non-zero on regression. It runs the model-free path, so it needs no key, no
billing and no network — which is what makes it affordable to gate *every* pull
request rather than only the ones where someone remembers.

| metric | tolerance |
|---|---|
| retrieval recall@1, recall@5, MRR | 0.02 absolute |
| routing accuracy | 0.02 absolute |
| refusal accuracy | 0.02 absolute |
| citation faithfulness | 0.02 absolute |
| fabricated citations | **zero** |
| unofficial citations | **zero** |
| over-refusal | 0.05, gated *upward* |
| cost per answer | 25% |

Over-refusal is gated upward because the cheapest way to make every other number
look good is to refuse more. Faithfulness is gated because of the quiet failure:
if the corpus rots in place and every citation goes `stale`, retrieval and
routing do not move at all — the system is still finding exactly the right span,
it has just stopped being able to vouch for it. Backdating the corpus by 400
days drops faithfulness to 0.753 and fails the build; every other metric holds
steady.

The gate has already earned its keep. A parser change dropped one noisy span,
which — because span ids were positional at the time — renumbered every span
below it and silently re-pointed every evaluation label at the wrong text. It
surfaced as a 12-point recall drop that was pure relabelling. Ids are now
content hashes, labels are content anchors that fail loudly, and both are pinned
by tests.

---

---

[← back to the README](../README.md)
