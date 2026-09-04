# Using founder-desk

*Running it, what it can be asked, and putting your own interface in front of it.*

[← back to the README](../README.md)

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

### The chat interface

```bash
founder-desk chat                        # a session at the terminal
```

```bash
pip install -e ".[serving]" && uvicorn serving.app:app --port 8123
```

Then open `http://localhost:8123`. Both are sessions rather than one-shot
queries, which is what makes the clarifying question usable — "do I need shops
and establishment registration?" → *"which state is the registered office in?"* →
"Maharashtra" → the answer. Facts you state carry forward, and only facts you
state: nothing is inferred.

The web UI is [municipal enamel signage](DESIGN.md). Every answer is a plate; the
coloured band is the authority tier of what it quotes; the plate's edge carries
freshness in line form as well as colour, so the coding survives greyscale. A
refusal is a struck plate that names what was searched. Sessions live in memory
and die with the process — nothing about your company is written to disk.

Other extras: `.[rerank]` for the cross-encoder (**recommended** — it is the
refusal gate), `.[browser]` plus `playwright install chromium` for the
client-rendered sources.

## Putting your own UI in front of it

You do not need to read anything else in these docs to do this. Run the service,
POST to one endpoint, render four cases.

```bash
pip install -e ".[serving,rerank]"      # rerank is optional but is the refusal gate
python -m ingest.build_corpus           # once; the corpus is committed, this refreshes it
FOUNDER_DESK_CORS_ORIGINS=http://localhost:3000 uvicorn serving.app:app --port 8123
```

Or, in one command, [with Docker](../Dockerfile).

**CORS is the first wall you will hit.** A UI on `localhost:3000` calling
`localhost:8123` is cross-origin, and without `FOUNDER_DESK_CORS_ORIGINS` the
browser blocks the request and tells you almost nothing about why.

### The endpoints

| | | For |
|---|---|---|
| `POST /chat` | `{session_id, message}` → `{answer, known, resolved_from_pending}` | A chat UI. Session state is held server-side; the client only keeps an id |
| `POST /ask` | `{question, state?, entity?}` → `Answer` | A one-shot search box, no session |
| `GET /sources` | The allowlist with publisher, tier, licence, status | An "about the data" page |
| `GET /ready` | 200 once the corpus is loaded | Health checks. `/health` only says the process is up |
| `GET /docs` | OpenAPI | Generating a typed client instead of hand-writing one |

### What comes back

A real response, trimmed:

```jsonc
{
  "answer": {
    "kind": "grounded",                       // ← four possible values, see below
    "applies_to": { "entity_type": "opc", "state": null, "turnover_band": null },
    "claims": [
      { "text": "Yes. One Person Companies are eligible to avail benefits…",
        "supported_by": ["startupindia-faq:dd4b3824"] }
    ],
    "cited_spans": [
      { "span_id": "startupindia-faq:dd4b3824",
        "citation": "Startup India Frequently Asked Questions - Q: Would a One Person Company…",
        "url": "https://www.startupindia.gov.in/content/sih/en/about_us/faqs.html",
        "publisher": "DPIIT / Startup India",
        "authority_tier": 3,                  // 1 statute · 2 notification · 3 guidance · 4 NOT government
        "fetched_at": "2026-09-03T23:31:57Z",
        "status": "current" }                 // or stale / superseded
    ],
    "as_of": "2026-09-04T18:25:53Z",
    "disclaimer": "INFORMATION GROUNDED IN PUBLISHED SOURCES - NOT PROFESSIONAL ADVICE…"
  },
  "known": "entity: opc",                     // facts carried forward this session
  "resolved_from_pending": false              // true when this message answered a clarify
}
```

### The four cases your UI must handle

A UI that renders only `grounded` will show blank screens three ways out of
four, and those three are where most of the value is.

| `kind` | Render | Field to read |
|---|---|---|
| `grounded` | The claims, each with its citation | `claims`, `cited_spans` |
| `clarify` | The question, and let them answer it in the next message | `clarifying_question` |
| `informational_only` | The factors, and that a CA or CS should decide | `considerations` |
| `refused` | That it cannot answer, and what it searched | `searched` |

`clarify` is the one worth building well: the next message is treated as the
answer to it, so *"do I need shops and establishment registration"* → *"which
state?"* → *"Telangana"* → the answer works with no extra API surface. Set
`resolved_from_pending` aside for the heading — when it is true, the answer is to
the **earlier** question, and showing the last message as the heading reads as a
non-sequitur.

### Three things you must not drop

These are the product, not decoration:

1. **The citation.** Publisher, tier, URL and fetch date beside every claim. An
   answer without them is the thing this exists to replace.
2. **`authority_tier: 4`** — not a government source. Say so visibly; the CLI
   and the bundled UI both do.
3. **`status` other than `current`** — the source is past its refresh window.
   Flag it rather than quietly serving it.

The bundled UI in [`serving/static/`](../serving/static/) does all of this in
about 200 lines of vanilla JS, and is worth reading as a reference before
writing your own.

### Or skip HTTP entirely

```python
from agent.answerer import build_answerer
from agent.conversation import Conversation

chat = Conversation(build_answerer())  # loads the corpus once, ~10s with models
turn = chat.ask("do I need shops and establishment registration")
print(turn.answer.kind, turn.answer.clarifying_question)
print(chat.ask("Telangana").answer.claims[0].text)
```

Build the answerer **once** and keep it: it holds the corpus, the index and the
models in memory, so constructing one per request would reload all of it.

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

---

[← back to the README](../README.md)
