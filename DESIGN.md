# founder-desk — visual world

**Municipal enamel signage.** Vitreous enamel plates of the kind screwed to
Indian municipal buildings and street corners: a deep enamel ground, a porcelain
face, a thick fired edge, rivets at the corners. Chosen because this product's
job is the same as a signage system's — state something official, legibly,
without editorialising, and make the authority behind it visible at a glance.

The governing rule: **an answer is a plate.** One plate at a time, generous
ground around it, never a grid of cards.

## Palette — a closed legend

Colour is not decoration here. Every hue means exactly one thing, and nothing
outside this table may be coloured.

| token | value | means |
|---|---|---|
| `--enamel` | `#0d2438` | the fired ground; all chrome |
| `--enamel-deep` | `#081827` | recessed ground, the ask bar well |
| `--porcelain` | `#f4efe4` | the plate face — the only reading surface |
| `--ink` | `#191713` | body text on porcelain |
| `--ink-soft` | `#6b6255` | secondary text, tinted from the porcelain hue, never grey |
| `--cream` | `#e8e2d4` | text on enamel ground |
| `--tier-statute` | `#7d2b23` | authority tier 1 — Act or Rules |
| `--tier-instrument` | `#a8722a` | authority tier 2 — notification, circular, direction |
| `--tier-guidance` | `#2e6a4a` | authority tier 3 — official guidance |
| `--signal` | `#d4491f` | **reserved**: the active plate, the caret, focus. Nothing else. |

*Raise, from the orienteering map:* the legend is closed and one hue is reserved
for the active leg only. A colour that means two things means nothing.

## State is line form, not hue

*Raise, from the emission-line rail:* every state is legible in greyscale,
because a compliance tool must not encode "this citation is out of date" in a
colour alone.

| state | plate edge |
|---|---|
| current | solid |
| stale | dashed |
| superseded | doubled |
| refused | a struck bar across the plate face |

Tier colour and state line-form are independent and both always present.

## Designed absence

*Raise, from the seven-segment display:* the unlit segments are designed too. The
refusal plate and the first-run empty plate carry the same craft as an answer —
a struck plate that names what was searched is a designed state, not a shrug.

## Composition

*Raise, from the Saville catalogue sleeve:* one element owns the field. A single
plate holds the answer; citations rivet beneath it as small code plates; nothing
competes.

- Type: one grotesque, one family, fixed rem scale, ratio ~1.2. Operate mode
  permits a system stack and that is what ships; the character lives in the
  plate system, not in a display face.
- Devanagari pairs the Latin on **standardised labels only** (the legend keys),
  as a municipal plate does. Never on source content — the sources are English
  and paraphrasing them would break the grounding contract.
- Prose measure 65–75ch on the plate face.
- Motion: enamel does not slide. State changes settle in 160–200ms; there is no
  page-load choreography.

## Browser surfaces

Selection, caret, focus ring, and scrollbar are themed from this palette. A
default focus ring on an enamel plate is the tell that a page was assembled
rather than built.
