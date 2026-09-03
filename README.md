# founder-desk

Grounded answers to the compliance questions a new Indian company hits in its
first year — GST, provident fund, DPIIT recognition, incorporation — where
**every claim is a verbatim quote from a primary government source**, stamped
with the URL and the date it was fetched.

When the sources cannot answer, it says so and lists what it searched. It never
writes a plausible sentence to fill the gap.

> **Information grounded in primary sources — not professional advice.** Quotes
> are reproduced from official government publications and may have been amended
> since they were fetched. Nothing here replaces a qualified chartered
> accountant, company secretary or lawyer.

---

## The problem

The authoritative text exists, is free, and is unusable. A founder's first year
touches MCA, CBIC, CBDT, DPIIT, EPFO, ESIC and a state government at once, in
statute, notification and FAQ form, across a dozen portals with no common
search. What ranks on Google instead is professional-firm content marketing:
undated, uncited, and often stale by one or more amendments.

So the gap is not "a chatbot that knows about GST". It is **a system that refuses
to answer without quoting a primary source, and knows when its source went out of
date.** Both halves are load-bearing, and both are enforced in code rather than
requested in a prompt.

## What an answer looks like

```
$ founder-desk ask "can a one person company get startup india benefits"

Q: can a one person company get startup india benefits
   [entity: opc · state: all-India]

  Yes. One Person Companies are eligible to avail benefits under the Startup
  India initiative.

  sources
    Startup India Frequently Asked Questions - Q: Would a One Person Company
    (OPC) be eligible to avail benefits under the Startup India initiative?
      DPIIT / Startup India · official guidance · fetched 2026-09-03
      https://www.startupindia.gov.in/content/sih/en/about_us/faqs.html
```

And when it cannot:

```
$ founder-desk ask "by when must I file INC-20A"

  I cannot ground an answer to this in the allowlisted sources, so I am not
  going to guess. This is either outside what this tool covers, or in a domain
  whose sources could not be collected - see the coverage table below.

  searched 13 official sources: ...
```

That second one is the interesting case. INC-20A is exactly the kind of question
this project exists for, and the corpus is full of confident, correctly-cited
spans about *other* filing deadlines. Answering from one of them would produce a
wrong answer that looks perfectly sourced.

---

## Four outcomes, and only one is an answer

| outcome | when | what it returns |
|---|---|---|
| `grounded` | the corpus covers it | claims, each quoting a cited span |
| `clarify` | the topic is state law and no state was given | the specific question needed |
| `informational_only` | it asks for a recommendation | the factors, and who should decide |
| `refused` | nothing supports an answer | what was searched, and nothing else |

The checks that rule out an answer run **before** retrieval, deliberately. Once a
plausible span is on screen the temptation is to use it.

*Clarify* exists because state law is the most common way to be confidently
wrong here — Shops & Establishments, professional tax and stamp duty all differ
by state. The router will not infer a state from a city, because a registered
office can sit in a different state from the operation:

```
$ founder-desk ask "do I need shops and establishment registration in Mumbai"

  This depends on your state - the rules you are asking about are state law.
  You mentioned Mumbai, but a company's registered office can sit in a
  different state from where it operates, so I will not assume. Which state is
  the registered office in?
```

---

## How "vetted by official sources only" is enforced

Not by a ranking preference. By a validator.

[`sources/sources.yaml`](sources/sources.yaml) is the only path into the index,
and [`sources/loader.py`](sources/loader.py) rejects any entry that is not
published on an official government host, or that omits a licence, or that omits
a refresh window. A CA firm's blog cannot be added to this project even by
someone who wants to — the loader raises.

```python
SourceEntry(url="https://example-ca-firm.com/gst-guide", ...)
# ValueError: 'example-ca-firm.com' is not an official government host.
# Allowed suffixes: .gov.in, .nic.in, rbi.org.in. Commentary, news and
# professional-firm content are out of scope by design.
```

Sources carry an **authority tier**, because the difference matters and the
system should be auditable on it:

| tier | what it is | in this corpus |
|---|---|---|
| 1 | statute and rules | 69 spans |
| 2 | notifications, circulars, RBI master directions | 1 span |
| 3 | official guidance — portal FAQs, department help pages | 471 spans |

The tier-3 skew is honest and is the single biggest weakness of the current
corpus: departmental FAQs are what these portals actually publish as HTML, while
the Acts and Rules sit behind PDFs and blocked hosts.

**Licences are declared, not assumed.** Every entry names the terms it is reused
under and carries `license_verified: false` until a human has actually read that
portal's terms. None have been read yet, and the field says so rather than
implying diligence that has not happened.

---

## The corpus

541 spans, 298,628 characters, from 13 of 17 allowlisted sources.

| domain | spans | note |
|---|---|---|
| gst | 319 | CBIC FAQs + GST portal help |
| labour | 191 | EPF & MP Act 1952, EPFO FAQs |
| startup_india | 36 | DPIIT recognition, self-certification |
| tax_registration | 4 | Income Tax portal only |
| banking_fema | 1 | RBI master directions index only |
| **incorporation** | **0** | **see below** |

### What could not be collected, and why

This is the part most likely to be quietly omitted, so it is stated first.

| source | reason |
|---|---|
| MCA portal | HTTP 403 to any non-browser client |
| India Code (Companies Act 2013) | HTTP 403 to any non-browser client |
| Ministry of Labour | HTTP 403 to any non-browser client |
| ESIC | TLS failure — incomplete certificate chain |

**Incorporation has zero coverage as a result.** SPICe+, INC-20A, ROC filing
deadlines and director requirements are all unanswerable, and the system refuses
them. They stay listed in the allowlist rather than being deleted, so the gap
shows up in the coverage report instead of disappearing.

Two things were *not* done to get around this. A browser User-Agent was not
spoofed, because these services have said no in the way a service says no. And
certificate verification was not disabled for ESIC, because a tampered response
would then be indistinguishable from a real one — an unacceptable trade for text
the system quotes as law.

### Collection etiquette

One request per second, serialised; an honest User-Agent naming the project and
a contact address; cached and resumable, so re-runs cost the source nothing.

```bash
python -m ingest.build_corpus     # fetch, parse, persist (cached; ~15s cold)
python -m ingest.watch            # re-fetch and diff against the corpus
```

---

## Freshness is tracked, not assumed

Indian compliance rarely breaks because a system invented law. It breaks because
a notification amended the position and the answer kept quoting the old one,
confidently and with a real citation.

Every span carries the instrument's date, the fetch date, and a hash of the
source's readable text. `ingest/watch.py` re-fetches and diffs those hashes;
changed sources mark their spans `needs_review`, and spans past their source's
refresh window go `stale` and are flagged in the answer. A weekly CI job runs it.

The hash is taken over *extracted text with whitespace normalised*, not raw
bytes — government portals stamp build ids and session tokens into their markup,
so a byte hash would report a change on every fetch and the signal would be
noise.

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

### Does the cross-encoder earn its place?

`python -m eval.runner --compare-rerank`, same 65 questions:

| | recall@1 | recall@3 | recall@5 | MRR | routing | latency |
|---|---|---|---|---|---|---|
| hybrid only | 0.610 | 0.805 | 0.854 | 0.713 | 0.862 | 0.38 ms |
| + cross-encoder | **0.707** | **0.854** | **0.902** | **0.782** | 0.862 | 665 ms |

`BAAI/bge-reranker-base`, CPU. It buys about 10 points of recall@1 for roughly
1,750× the retrieval latency, plus a 2 GB dependency and a 13-second model load.
Worth it for a batch or an API with a budget; not worth it for the default path,
so it is opt-in behind `pip install -e ".[rerank]"` and the base install stays
light.

Getting this comparison to be *meaningful* required a fix worth describing. When
the refusal gate read the reranked list, the cross-encoder improved retrieval and
made routing **worse** (0.862 → 0.815, over-refusal 0.122 → 0.195): it promotes
spans that are semantically apt but share fewer words with the question, so they
won the ranking and then failed a lexical gate. "Can this be answered" is a
property of what was retrieved, not of the order it ended in — so the gate reads
the first-stage candidates and the reranker only chooses what to quote. Routing
is now identical across both, which is the property that makes the row above a
fair comparison rather than two different systems.

---

## Evaluation

65 questions in [`eval/questions.yaml`](eval/questions.yaml): 41 answerable, 12
that must be refused, 7 that must ask for a state, 5 that must decline to
recommend.

Every answerable question is a **paraphrase**, never the source's own wording.
The corpus is built from FAQ pages, so the lazy version — copy each source
question and label it with its own span — would measure string matching and
report near 1.00. A test enforces this ([`test_questions_are_paraphrases_not_copies`](tests/test_eval_dataset.py)),
and it caught one verbatim question in this very file.

Gold labels reference **a phrase from the source question**, not a span id, and
resolve at load time. Ambiguous or missing anchors are a hard error.

### Results

Model-free retrieval baseline, `$0.0000` per answer:

| retrieval (n=41) | |
|---|---|
| recall@1 | 0.610 |
| recall@3 | 0.805 |
| recall@5 | 0.854 |
| recall@10 | 0.878 |
| MRR | 0.713 |

| routing (n=65) | |
|---|---|
| overall | 0.862 |
| grounded | 0.878 |
| clarify | 1.000 |
| informational_only | 1.000 |
| refused | 0.667 |
| over-refusal | 0.122 |

| citation faithfulness (69 citations) | |
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

- **65 questions is small.** Recall@5 of 0.854 means six misses. Treat the third
  decimal as noise.
- **Refusal accuracy is 0.667, the weakest number here**, and it is reported
  next to over-refusal on purpose: refusing everything would score 1.000 on one
  and destroy the other. The four questions wrongly answered are incorporation
  ones where a GST or PF span shares enough vocabulary to clear the gate.
- **Routing accuracy is not answer correctness.** It measures whether the system
  chose the right *kind* of response and retrieved the right span — not whether
  a reader would be well served by the quote.
- **The corpus is 87% tier-3 guidance.** These numbers describe finding the
  right FAQ entry, which is a lower bar than reading the Act.

### The refusal threshold was swept, not chosen

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

### Two measurements that overturned the obvious approach

**The normalised score cannot refuse anything.** Min-max normalising hybrid
scores makes the top hit ~1.0 regardless of quality — "how do I train a neural
network" retrieved a span scoring 0.96. Raw BM25 was the next candidate and also
fails: 8.5 for an off-topic capital-gains question against 6.9 for an in-scope
incorporation one. The gate is IDF-weighted query coverage instead, and the two
rejected signals are kept on every hit for diagnostics.

**Word-repetition does not identify navigation chrome.** The intuition — menus
repeat their labels, prose does not — is backwards for legal text. The EPF Act's
densest passages score 0.33 unique words because statutes repeat defined terms;
a Startup India link menu scores 0.72. Filtering on it removed 71 of 77 statute
chunks and kept the menus. Sentence-terminator count separates them cleanly
(menus: 0, statute prose: 4–81) and is what ships.

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

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ingest]"
python -m ingest.build_corpus
pytest -q
```

```bash
founder-desk ask "do traders under 20 lakh turnover need GST registration"
founder-desk ask "do I need professional tax registration" --state MH
founder-desk sources
```

Optional extras: `.[rerank]` for the cross-encoder, `.[serving]` for the API
(`uvicorn serving.app:app`, with `/ask`, `/sources`, `/health`, `/ready`).

## Layout

```
sources/     the allowlist and its validator - the only path into the index
ingest/      fetch, parse, persist, and the freshness watcher
agent/       router, answerer, output contract
agent/retrieval/  hybrid store, hashing embedder, reranker protocol
eval/        question set, metrics, groundedness judge, CI gate
serving/     CLI and FastAPI service
```

## Status

| area | state |
|---|---|
| Allowlist + licence/host enforcement | ✅ measured |
| Ingestion, 13 sources, 541 spans | ✅ measured |
| Freshness ledger + weekly CI job | ✅ built; no upstream change observed yet |
| Hybrid retrieval | ✅ measured |
| Cross-encoder reranking | ✅ measured (opt-in) |
| Router, refusal, clarify, judgement guard | ✅ measured |
| Evaluation + CI gate | ✅ measured |
| Incorporation domain | ❌ **no coverage** — sources blocked |
| Model-backed synthesis (`agent/llm.py`) | ⚠️ protocol + offline stub only; **never run against a live model** |

Every number in this README comes from a command in it. Nothing model-backed has
been run, and nothing in the measured path needs it.

112 tests · `ruff` · `mypy --strict`

## Licence

MIT for the code. The corpus is reproduced from Government of India sources
under the terms named per entry in `sources/sources.yaml`; those terms have not
yet been individually verified, and `license_verified` is `false` throughout.
Confirm before republishing a derived mirror.
