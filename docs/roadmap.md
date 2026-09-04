# Roadmap

*The same plan seen twice: as capabilities a founder notices, and as capabilities the system gains.*

[← back to the README](../README.md)

---

## Roadmap — product phases

What a founder would notice, ordered by who it helps rather than by difficulty.
Each phase is shippable alone. The engineering view of the same work is in
[engineering phases](#roadmap--engineering-phases) below.

| # | Phase | Why a founder needs it | Done when |
|---|---|---|---|
| ✅ | **Sourced answers, or an honest refusal** | Search returns undated, uncited firm content | Every claim quotes a source with a date, or refuses |
| ✅ | **Company setup: entity types, DIN, PAN, bank account** | The first questions anyone asks, and the ones it used to refuse | Entity types, DIN, PAN and account-opening documents answer with citations |
| 🔶 | **The states founders register in** | Shop registration, professional tax and stamp duty are state law | Per state: is registration required, by when, hours rules, professional tax |
| ⬜ | **"What am I supposed to be doing?"** | The real failure is the question nobody knew to ask; penalties follow | A profile produces a dated task list, every item citing its rule |
| ⬜ | **Tell me when the rules change** | An answer right in March can be wrong in April | A weekly digest has caught one real amendment end to end |
| ⬜ | **Answer in the founder's language** | State law is published in-language first, English late or never | A Marathi question returns a Marathi answer from Marathi source text |
| ⬜ | **Clear it for other people to use** | The first question anyone asks of a public tool | Every source carries a checked licence, not an assumed one |

**Phase 2 is partial:** Delhi, Haryana and Telangana are covered. Karnataka and
Maharashtra are not, and the reasons are mechanical rather than editorial — see
[What could not be collected, and why](corpus.md#what-could-not-be-collected-and-why).

**Phase 3 depends on 1 and 2.** A first-year checklist is only as trustworthy as
the coverage beneath it, and one that silently omits company setup is worse than
none at all.

## Roadmap — engineering phases

The same work seen from the code. Where a product phase says *what a founder can
ask*, this says *what capability the system gains* — and every open one is gated
by a missing capability rather than by effort.

| # | Capability | Product phase it serves | State |
|---|---|---|---|
| E1 | Allowlist with host, licence and refresh validation | all | ✅ |
| E2 | Cached, rate-limited ingestion; content-hash freshness ledger | all | ✅ |
| E3 | Hybrid BM25 + vector retrieval, in-memory, 0.38 ms p50 | all | ✅ |
| E4 | Four-outcome answer contract with grounding enforced by validator | all | ✅ |
| E5 | Evaluation harness and two committed CI baselines | all | ✅ |
| E6 | Headless rendering for client-side portals | company setup | ✅ |
| E7 | Cross-encoder relevance gate for refusals | all | ✅ |
| E8 | Embedding model behind the same protocol | all | ✅ |
| E9 | Jurisdiction scoping + stratified retrieval by state | states | ✅ |
| E10 | Tier-4 external sources, declared and surfaced | PAN | ✅ |
| E11 | **PDF text extraction in ingestion** | statute depth | ⬜ born-digital only; `pypdf` already a dependency |
| E12 | **OCR** | Karnataka | ⬜ its Shops Act is scanned images |
| E13 | **Legacy-font transcoding** | Maharashtra | ⬜ its Rules are non-Unicode Marathi |
| E14 | **Multilingual embedder and reranker** | in-language answers | ⬜ current pair is English-only |
| E15 | **Structured entity/deadline model** | the checklist | ⬜ needs facts, not spans |

E11 is the cheapest and unlocks the most: most Indian statute is published as
PDF, which is why the corpus is 86% departmental guidance rather than law.

---

[← back to the README](../README.md)
