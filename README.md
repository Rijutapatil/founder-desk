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

## What you can ask it

The corpus covers the first year: GST, provident fund and contract labour,
DPIIT recognition, and incorporation. Below is what actually works today, with
the real answer each returns.

**GST — registration, thresholds and returns** (320 spans, the deepest area)

```bash
founder-desk ask "do traders under 20 lakh turnover need GST registration"
founder-desk ask "I take on projects in several states - do I need a GST number in each"
founder-desk ask "if I register voluntarily under 20 lakh, do I pay tax from my first sale"
founder-desk ask "can I hold two GST registrations on one PAN"
founder-desk ask "I provide services and turn over 50 lakh - can I opt for composition"
founder-desk ask "we deal only in exempt goods but are registered - do we file returns"
```

**Provident fund and contract labour** (141 spans)

```bash
founder-desk ask "if someone's basic plus DA is above 15000, must they join EPF"
founder-desk ask "can I recover the employer's PF share from my employee's salary"
founder-desk ask "does an apprentice have to be enrolled in provident fund"
founder-desk ask "at how many contract workers must my establishment register"
founder-desk ask "what happens if a principal employer never registers for contract labour"
```

**DPIIT / Startup India recognition** (35 spans)

```bash
founder-desk ask "can a one person company get startup india benefits"
founder-desk ask "which papers do I upload to get DPIIT recognised"
founder-desk ask "how long does the recognition certificate take"
founder-desk ask "can a foreign national be an LLP partner and still register with startup india"
```

**Incorporation** (1 span — see the coverage table)

```bash
founder-desk ask "which kinds of company can I set up in India"
```

### And what it does instead of answering

Three of the four outcomes are not answers, and they are the point.

```bash
# Asks, because this is state law and no state was given
founder-desk ask "do I need shops and establishment registration in Mumbai"

# Gives factors and names who should decide - never a recommendation
founder-desk ask "should I register an LLP or a Pvt Ltd"

# Refuses: in scope, but the source is uncollectable
founder-desk ask "by when must I file INC-20A"

# Refuses: outside what this covers
founder-desk ask "how do I get an FSSAI licence for a food business"
founder-desk ask "who won the cricket world cup"
```

Every example above was run before being written down, and behaves as shown.

**Refusal is still the weakest behaviour**, though much less so than it was: at
0.654 it is the lowest number in the evaluation. What remains is a specific,
nameable class — questions that are squarely about a topic the corpus covers,
asking something inside it that the corpus does not contain. "How many people
must be on the board of a private company" is about incorporation, and the one
incorporation span *is* about companies; it simply says nothing about boards. No
relevance score separates those, because the span genuinely is relevant. Telling
them apart is question-answering, not retrieval.

Add `--state MH` (any ISO 3166-2:IN code) or `--entity pvt-ltd|llp|opc|sole-prop`
to answer for a specific situation, and `founder-desk sources` to see every
source it is allowed to read.

---

## What AI is in the backend?

**None, by default.** No language model is called, no API key is needed, and
nothing leaves your machine except the requests that fetch the government pages
themselves. The only outbound calls anywhere in the package are in
`ingest/fetch.py`.

| stage | what actually runs |
|---|---|
| lexical retrieval | **BM25** — a ranking function from 1994. Arithmetic over term frequencies. |
| semantic retrieval | **Character n-gram feature hashing** — a hash function, not a trained model. Deterministic and offline. |
| answering | **Extractive.** The answer *is* the source's sentences, returned verbatim. There is no generation step. |
| reranking *(optional, off)* | **`BAAI/bge-reranker-base`**, a local cross-encoder. The only neural network in the project. Downloads once, runs on your CPU, and only *reorders* candidates — it never writes text. |

That is a design choice, not a limitation waiting to be fixed. Fabrication is
impossible here by construction rather than by prompt: there is no step at which
a sentence could acquire a fact the corpus does not contain. It also means the
whole evaluation runs for `$0.0000` with no key, which is why the CI gate can
afford to check every pull request.

`agent/llm.py` defines a `StructuredModel` protocol for optionally synthesising
several quotes into connected prose. It is **imported by nothing** — not the
answerer, not the evaluation, not the service — and has never been run against a
live model. If it is ever wired up, the groundedness judge and its zero-tolerance
fabrication gate are already in place to police it.

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
| 1 | statute and rules | 27 spans |
| 2 | notifications, circulars, RBI master directions | 1 span |
| 3 | official guidance — portal FAQs, department help pages | 468 spans |

The tier-3 skew is honest and is the single biggest weakness of the current
corpus: departmental FAQs are what these portals actually publish as HTML, while
the Acts and Rules sit behind PDFs and blocked hosts.

It got *worse*, deliberately, when the fragment and contents-page filters landed:
tier-1 spans fell from 70 to 27. The chunks removed were real statute text and
correctly cited, but they opened mid-sentence or were pure section-number lists,
and quoting one next to a clean answer makes the good quote look less
trustworthy rather than the fragment more so. Fewer, readable statute spans is
the right trade at this corpus size; properly parsing the Act into sections is
the fix, and it has not been done.

**Licences are declared, not assumed.** Every entry names the terms it is reused
under and carries `license_verified: false` until a human has actually read that
portal's terms. None have been read yet, and the field says so rather than
implying diligence that has not happened.

---

## The corpus

499 spans, 238,854 characters, from 16 of 21 allowlisted sources.

| domain | spans | note |
|---|---|---|
| gst | 320 | CBIC FAQs + GST portal help |
| labour | 141 | EPF & MP Act 1952, EPFO FAQs, ESI Acts, contract labour |
| startup_india | 35 | DPIIT recognition, self-certification |
| tax_registration | 3 | Income Tax portal only |
| banking_fema | 1 | RBI master directions index only |
| incorporation | 1 | NSWS / Ministry of Corporate Affairs — **thin, see below** |

### What could not be collected, and why

This is the part most likely to be quietly omitted, so it is stated first.

| source | reason |
|---|---|
| MCA portal | HTTP 403 to any non-browser client |
| India Code (Companies Act 2013) | HTTP 403 to any non-browser client |
| Ministry of Labour | HTTP 403 to any non-browser client |
| NSWS full listing | renders, but the catalogue is a paginated React UI — see below |
| NSWS startup registration | renders, and is **empty upstream**: no "About this approval" text |

A browser User-Agent is not spoofed for the three that return 403. These are
public services that have said no in the way a service says no, and a test pins
that they are never routed through the renderer either.

**Incorporation is now covered, thinly.** One span, from the official Ministry
of Corporate Affairs page on NSWS: which entity types can be incorporated, the
governing Companies Act, and the stated processing time. That is enough to
answer "which kinds of company can I set up in India" and nowhere near enough for
SPICe+, INC-20A, AOC-4 or director requirements — all of which the system still
refuses.

### Headless rendering, and the line it does not cross

Some official portals build their pages in the browser. NSWS returns 29
characters of server HTML and assembles everything client-side, so a static
fetcher sees an empty shell however many times it asks — the same reason it would
be unreachable to a reader without JavaScript.

`ingest/render.py` drives headless Chromium for sources marked `render: true`,
at the same one-request-per-second rate and **with the same honest identifying
User-Agent as the plain fetcher**. What changes is only that the page's own
JavaScript runs. A site that declines to serve us still declines: the three hosts
returning 403 are not routed through the renderer, because using a browser to get
past a refusal is working around a "no" rather than reading a page written for a
browser.

Each rendered source names a `content_selector`. Taking the whole `<body>` wraps
every span in the site's header and footer — helpdesk number, ministry
navigation, translation notice, copyright — and repeated across a corpus that
boilerplate becomes common vocabulary, dragging on BM25 and diluting the quote a
reader sees. A selector that stops matching returns nothing and logs it, rather
than silently refilling the corpus with chrome.

The browser is an optional extra (`pip install -e ".[browser]" && playwright
install chromium`). The committed corpus means CI never needs it, and a missing
browser is reported per source with the command that fixes it rather than
failing the run.

NSWS's internal JSON API was found and not used: it returns HTTP 400 to a plain
request, and reverse-engineering an undocumented internal endpoint is a worse
citizen than rendering the page the portal actually offers the public.

### ESIC: fixed properly rather than worked around

ESIC was in the blocked list too. Its server sends only its leaf certificate and
omits the intermediate, so the chain cannot be built from a normal trust store.

Disabling certificate verification would have collected it in one line, and is
refused: a tampered response would then be indistinguishable from a real one,
which is an unacceptable trade for text this system quotes as law. Instead the
missing GlobalSign intermediate is committed under `sources/certs/` and supplied
explicitly. Validation still terminates at *GlobalSign Root CA - R6*, already in
certifi — a link was added to the chain, not removed from it.

Tests pin the certificate's SHA-256 fingerprint, assert it is an intermediate
rather than self-signed (a self-signed pin would be trust-on-first-use, not
verification), fail 90 days before it expires so rotation is scheduled rather
than discovered, and walk the AST of every ingest module to prove `verify=False`
appears nowhere.

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

## Evaluation

82 questions in [`eval/questions.yaml`](eval/questions.yaml): 44 answerable, 26
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
| recall@1 (n=44) | 0.636 | **0.727** |
| recall@5 | 0.864 | **0.932** |
| MRR | 0.734 | **0.805** |
| routing overall (n=82) | 0.732 | **0.878** |
| grounded | 0.864 | **0.977** |
| clarify | 1.000 | 1.000 |
| informational_only | 1.000 | 1.000 |
| refused | 0.385 | **0.654** |
| over-refusal | 0.136 | **0.023** |

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

- **82 questions is small.** Recall@5 of 0.932 means three misses. Treat the
  third decimal as noise.
- **Refusal accuracy is 0.654, still the weakest number here**, and it is
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

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ingest,rerank]"
python -m ingest.build_corpus
pytest -q
```

`.[rerank]` is worth the 2 GB. Without it the refusal gate falls back to a
lexical signal that is much worse at knowing what it does not know — 0.385
against 0.654 — and the CLI will tell you it is running in that mode.

```bash
founder-desk ask "do traders under 20 lakh turnover need GST registration"
founder-desk ask "do I need professional tax registration" --state MH
founder-desk sources
```

Optional extras: `.[rerank]` for the cross-encoder, `.[serving]` for the API
(`uvicorn serving.app:app`, with `/ask`, `/sources`, `/health`, `/ready`), and
`.[browser]` plus `playwright install chromium` for the client-rendered sources.

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
| Ingestion, 16 sources, 499 spans | ✅ measured |
| Freshness ledger + weekly CI job | ✅ built; no upstream change observed yet |
| Hybrid retrieval | ✅ measured |
| Cross-encoder reranking | ✅ measured (opt-in) |
| Router, clarify, judgement guard | ✅ measured |
| Refusal gate (lexical + cross-encoder) | ✅ measured, both baselines gated |
| Evaluation + CI gate | ✅ measured |
| ESIC via pinned intermediate certificate | ✅ measured |
| Headless rendering (optional extra) | ✅ measured |
| Incorporation domain | ⚠️ **1 span** — MCA and India Code refuse automated clients |
| Model-backed synthesis (`agent/llm.py`) | ⚠️ protocol + offline stub only; **never run against a live model** |

Every number in this README comes from a command in it. Nothing model-backed has
been run, and nothing in the measured path needs it.

145 tests · `ruff` · `mypy --strict`

## Licence

MIT for the code. The corpus is reproduced from Government of India sources
under the terms named per entry in `sources/sources.yaml`; those terms have not
yet been individually verified, and `license_verified` is `false` throughout.
Confirm before republishing a derived mirror.
