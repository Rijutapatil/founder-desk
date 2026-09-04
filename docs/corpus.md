# The corpus

*Which sources are admitted, how they are collected, and what could not be.*

[← back to the README](../README.md)

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

692 spans, 400,404 characters, from 25 of 42 allowlisted sources.

| domain | spans | note |
|---|---|---|
| gst | 320 | CBIC FAQs + GST portal help |
| labour | 276 | EPF & MP Act 1952, EPFO FAQs, ESI Acts, contract labour, **Delhi · Haryana · Telangana** |
| banking_fema | 44 | RBI Commercial Banks KYC Directions — what a bank must obtain to open an account |
| startup_india | 32 | DPIIT recognition, self-certification |
| tax_registration | 20 | Income Tax guidance for business income · **PAN, via a tier-4 source** |
| incorporation | 2 | NSWS / Ministry of Corporate Affairs — entity types and DIN. **Still thin** |

### What could not be collected, and why

This is the part most likely to be quietly omitted, so it is stated first.

| source | reason |
|---|---|
| MCA portal | HTTP 403 to any non-browser client |
| India Code (Companies Act 2013) | HTTP 403 to any non-browser client |
| Ministry of Labour | HTTP 403 to any non-browser client |
| NSWS full listing | renders, but the catalogue is a paginated React UI — enumerable with `ingest/discover_nsws.py` |
| NSWS startup registration | renders, and is **empty upstream**: no "About this approval" text |
| Karnataka Shops Act + Rules | scanned PDFs, no text layer — 65 pages yield 64 characters. Needs OCR |
| Maharashtra Shops Rules 2018 | text layer is legacy-font Marathi, extracts as mojibake |

A browser User-Agent is not spoofed for the three that return 403. These are
public services that have said no in the way a service says no, and a test pins
that they are never routed through the renderer either.

**Three states covered: Delhi, Haryana and Telangana.** Telangana's labour
department publishes ~46k characters of English Q&A and Haryana the Punjab Shops
Act as applied there, so both reach the standard Delhi set. The clarifying
question now names the states it can actually use, rather than asking for a fact
it may not be able to act on.

**Karnataka and Maharashtra remain out, and not for want of trying.** Karnataka and
Maharashtra were searched properly and neither can be collected to the standard
Delhi met — for mechanical reasons, each naming a different missing capability:
Karnataka publishes its Shops Act only as scanned images (OCR), Maharashtra
publishes its Rules in a legacy non-Unicode Marathi font (transcoding, and then
an Indic-capable embedder). The state portals' own HTML is either 82% Devanagari
or a thin forms menu — the shape already measured harmful. All three are listed
with their reasons rather than quietly omitted.

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

---

[← back to the README](../README.md)
