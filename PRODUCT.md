# founder-desk — product truth

Every fact below was confirmed in the sessions that built this project, not
inferred. Where something is an assumption it says so.

## What it is

A grounded question-answering system for the compliance questions a newly
incorporated Indian company hits in its first year. Every claim it makes is a
verbatim quote from a primary government source, stamped with the URL and the
date it was fetched — or it refuses and says what it searched.

## The meaningfully different mechanism

Not "an LLM that knows about GST". Three things it does that the alternatives
do not:

1. **It cannot answer without quoting.** Grounding is enforced by a validator,
   not requested in a prompt. A claim with no cited span raises.
2. **It refuses.** Four outcomes exist and only one is an answer: `grounded`,
   `clarify` (the topic is state law and no state was given),
   `informational_only` (the question asks for a recommendation), `refused`.
3. **It knows when its sources went stale.** Every span carries the instrument's
   date, the fetch date, and a content hash; a watcher diffs them weekly.

There is **no language model anywhere in the answering path**. BM25 plus
character n-gram hashing plus extractive answering. The optional cross-encoder
only reorders and gates refusals; it never writes text.

## Primary user and situation

A first-time founder in India, months 0–12 after incorporation, who does not
have a CA on retainer and is trying to work out what they are legally required
to do. They are searching at their desk, usually because something triggered the
question — a customer asked for a GSTIN, they hired their first employee, an
investor asked whether they are DPIIT recognised.

Secondary: the maintainer, checking coverage and freshness.

## The job

Get an accurate, dated, citable answer — or a clear "this is not covered" — fast
enough to act on, and know which of the two they got.

## Durable constraints that future work must preserve

- **Official sources only.** A validator rejects any source not published on
  `.gov.in`, `.nic.in` or `rbi.org.in`. Commentary is unrepresentable.
- **Information, not advice.** A disclaimer is re-stamped by a validator on every
  answer. The system never recommends; questions asking for a recommendation
  return factors and say a CA/CS/lawyer should decide.
- **Citations travel with claims.** Publisher, authority tier, URL and fetch date
  are part of the answer, not a footnote.
- **State matters.** Shops & Establishments, professional tax and stamp duty are
  state law. The system asks rather than assuming, and never infers a state from
  a city.
- **No fabricated numbers or claims** anywhere, including in UI mockups.
- **Honest status.** Coverage gaps are published, not hidden. Incorporation
  currently has one span; MCA and India Code refuse automated clients.

## Terminology the interface must use correctly

span · citation · authority tier (statute / notification / official guidance) ·
grounded · clarify · refused · stale · DPIIT · GSTIN · EPF · ESI · CLRA

## Evidence and assets

- Public repo: `github.com/Rijutapatil/founder-desk`
- 499 spans from 16 official sources; 82-question evaluation; 145 tests
- Measured numbers live in README.md and `eval/baseline_metrics*.json`
- No logo, no brand assets, no established visual identity. The only existing
  "surface" is a terminal CLI.

## Platform

`web` — a locally-served chat UI plus a terminal REPL. No hosted public app:
that was ruled out for v1 on 4 Sep 2026 and reaffirmed when the chat surface was
chosen.

## Stack

**Undecided — to be offered to the user.** The repo has no frontend scaffold and
no JS build tooling. FastAPI already serves the API, so plain static HTML/CSS/JS
served by it is the low-friction option, but the choice has not been made.

## Accessibility

Not yet specified. Assume keyboard operability and WCAG AA contrast as the floor
until told otherwise.
