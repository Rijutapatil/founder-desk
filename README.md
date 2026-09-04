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

## Why not just ask ChatGPT or Claude?

Because a general assistant answers. That is what it is for, and it is why they
are so useful — but a compliance question you cannot verify is worse than no
answer, because you will act on it.

Here, **refusing correctly is the feature.** Everything below is a mechanism in
this repository and a number from [`eval/baseline_metrics_reranked.json`](eval/baseline_metrics_reranked.json)
over 94 questions. Nothing is claimed that cannot be pointed at.

| | A general assistant | founder-desk | Where to check |
|---|---|---|---|
| When it doesn't know | Answers anyway | Refuses, and names what it searched | refusal **0.593** · over-refusal 0.036 |
| Where the answer came from | Training data; unattributable | One of 25 allowlisted sources, quoted word for word | [`sources/sources.yaml`](sources/sources.yaml) |
| Can you check it | No | Publisher, authority tier, URL and fetch date on every claim | `CitedSpan` in [`agent/schema.py`](agent/schema.py) |
| Is it current | Training cutoff; unknowable from the answer | Content-hashed and diffed weekly; stale citations flagged in the answer | [`ingest/watch.py`](ingest/watch.py) |
| Can it invent a rule | Yes | No — a claim citing nothing raises rather than renders | **fabricated 0.000** over 96 citations |
| Does it know your state | Generalises across India | Asks which state; refuses if it holds no source for that one | `_state_gap` in [`agent/answerer.py`](agent/answerer.py) |
| Will it give advice | Often | Never — returns the factors and says to see a CA or CS | `INFORMATIONAL_ONLY` |
| How often is it right | Cannot tell you | 94 questions, two baselines, gated on every pull request | [`eval/`](docs/evaluation.md) |
| Where your question goes | To a provider | Nowhere. No model is called; sessions live in memory | no LLM imported anywhere |

The last two rows are the ones that tend to matter in practice. A general
assistant cannot tell you how often it is right *about Indian compliance
specifically*, and it cannot promise that the details of your company stayed on
your laptop.

**The difference is enforcement, not instruction.** Prompting a model to cite
its sources is a request, and requests degrade quietly. Here, constructing an
answer whose claim cites nothing raises an exception
([`agent/schema.py`](agent/schema.py)). Fabrication is not unlikely — it is
unrepresentable.

### Where a general assistant is the better tool

This section would be worth nothing if it only listed advantages — that is
precisely the kind of one-sided, unsourced content this project exists as an
alternative to. So, plainly:

- **Breadth.** ChatGPT and Claude will attempt any question you have. This
  covers six domains of first-year compliance across three states and refuses
  everything else, including questions a founder legitimately needs answered.
- **Fluency.** They compose an answer for you. This quotes, so replies read like
  a government FAQ — because they are one.
- **Nothing to set up.** A browser tab against a clone, a corpus build and a
  2 GB optional download.
- **They improve without you.** This improves when someone adds a source.

And the two weakest numbers here, stated in the same breath as the strong ones:
refusal accuracy is **0.593**, the lowest figure in the
project — roughly two in five questions that should be declined still get an
answer. And 85% of the corpus is departmental guidance rather than
statute, so most answers quote what a department *says about* the law rather
than the law itself.

The honest summary: if you want an answer to anything, ask a general assistant.
If you want to know whether an answer is checkable, and to be told plainly when
it is not, that is the thing this does that they do not.

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

## The rest of the documentation

This page is the short version. Each document below stands on its own.

| | |
|---|---|
| [Using it](docs/using-it.md) | Running it, what it can be asked, and **putting your own UI in front of it** |
| [How it works](docs/how-it-works.md) | The stack, which AI framework is and is not used, what state it keeps, and how the files connect |
| [The corpus](docs/corpus.md) | Which sources are admitted and how that is enforced · what could not be collected · freshness |
| [Retrieval](docs/retrieval.md) | Hybrid search, the embedding model, the reranker, and the refusal gate |
| [Evaluation](docs/evaluation.md) | What is measured, what the numbers mean, and what the CI gate enforces |
| [Roadmap](docs/roadmap.md) | Product phases and engineering phases |

Design decisions for the web UI are in [DESIGN.md](DESIGN.md); durable product
truth in [PRODUCT.md](PRODUCT.md).

## Status

| area | state |
|---|---|
| Allowlist + licence/host enforcement | ✅ measured |
| Ingestion, 16 sources, 499 spans | ✅ measured |
| Freshness ledger + weekly CI job | ✅ built; no upstream change observed yet |
| Hybrid retrieval | ✅ measured |
| Cross-encoder reranking + embedding model | ✅ measured (opt-in extra) |
| Router, clarify, judgement guard | ✅ measured |
| Company setup: entity types, DIN, PAN, bank-account KYC | ✅ measured |
| External (tier-4) sources, declared and surfaced | ✅ measured |
| State law: scoped answers, others refused | ✅ measured (DL · HR · TG) |
| Refusal gate (lexical + cross-encoder) | ✅ measured, both baselines gated |
| Chat: terminal REPL + local web UI | ✅ built and exercised in a browser |
| Evaluation + CI gate | ✅ measured |
| ESIC via pinned intermediate certificate | ✅ measured |
| Headless rendering (optional extra) | ✅ measured |
| Incorporation domain | ⚠️ **1 span** — MCA and India Code refuse automated clients |
| Model-backed synthesis (`agent/llm.py`) | ⚠️ protocol + offline stub only; **never run against a live model** |

Every number in this README comes from a command in it. Nothing model-backed has
been run, and nothing in the measured path needs it.

203 tests · `ruff` · `mypy --strict`

## Licence

MIT for the code. The corpus is reproduced from Government of India sources
under the terms named per entry in `sources/sources.yaml`; those terms have not
yet been individually verified, and `license_verified` is `false` throughout.
Confirm before republishing a derived mirror.
