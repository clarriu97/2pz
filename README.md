# Bedashing Network Intelligence

[![CI](https://github.com/clarriu97/2pz/actions/workflows/ci.yml/badge.svg)](https://github.com/clarriu97/2pz/actions/workflows/ci.yml)
[![coverage 97.82%](https://img.shields.io/badge/pipeline%20coverage-97.82%25-3fb98a)](https://github.com/clarriu97/2pz/actions/workflows/ci.yml)
[![tests 531](https://img.shields.io/badge/tests-313%20python%20%2B%20218%20web-4a9ede)](https://github.com/clarriu97/2pz/actions/workflows/ci.yml)

**AI-enabled geospatial decision support for retail network right-sizing.**

Live: **[2pz.larri.dev](https://2pz.larri.dev)** · Five-minute guided demo: **[docs/walkthrough.md](docs/walkthrough.md)**

---

## What it decides, and for whom

For the **Head of Retail Portfolio** at [Bedashing Beauty Lounge](https://bedashingbeauty.com), a
premium UAE salon chain with 23 lounges — the one role that signs a lease, funds a refit, or lets a
site go. Three questions a portfolio review has to settle:

| Question | Output |
|---|---|
| Which lounges are earning their footprint? | `PROTECT` · `HOLD` · `SHRINK` per branch |
| Where are we paying rent twice for the same customer? | self-overlap between our own catchments |
| Where is there demand we do not reach? | `GROW` · `WATCH` · `SKIP` per candidate zone |

**It currently says: 2 PROTECT · 15 HOLD · 6 SHRINK, and 17 of 573 scored cells are `GROW`.**

The finding that matters: **Ministry Area shares 65% of its catchment with two of our own lounges,
Al Maqta 61%.** Both are individually strong branches — Ministry Area scores 0.71 on strength, fifth
best of 23 — and both are flagged `SHRINK` purely because our own network already covers their
ground. That is a consolidation decision, not a performance problem, and a single-score ranking
would have buried it.

---

## Run it

The product is static: all scoring happens offline in a Python pipeline whose output is committed,
so **no API key is needed to see the whole thing**.

```bash
cd web && npm install && npm run dev
```

That is the complete product except the live chat, which proxies OpenAI. The 101 pre-generated
analyst notes are committed, so the AI layer is visible without a key. To run the chat too:
`cp .dev.vars.example .dev.vars`, add `OPENAI_API_KEY`, then `npm run build && npm run dev:pages`.

Rebuilding the dataset is optional — every remote response is cached under `data/raw/` and
committed, so this is fully offline and reproduces the committed output byte for byte:

```bash
uv sync && uv run python -m pipeline.run
```

---

## The decision model

A two-axis matrix, **not** machine learning. A portfolio committee has to defend a lease decision to
a CFO, and "the gradient boosting said so" is not a defence. Because every score is a weighted sum
of normalised signals, the explanation is not an approximation of the model — it *is* the model, and
a Pydantic validator refuses to build a score whose contributions do not sum to it.

```
X — branch strength                      Y — market attractiveness & defensibility
  rating (4.20–4.95 band)     +0.30        catchment demand (built form)   +0.45
  log review volume           +0.25        competitive headroom            +0.35
  momentum  (simulated)       +0.20        self-cannibalisation            −0.20
  position vs local rivals    +0.25

PROTECT   strength ≥ 0.65 AND market ≥ 0.47
SHRINK    strength < 0.51 OR (market < 0.40 AND self-overlap ≥ 45%)
HOLD      everything else

zones     0.45·demand + 0.35·coverage gap − 0.20·saturation
          GROW ≥ 0.62 · WATCH ≥ 0.45 · SKIP below, or below a 0.12 demand floor
```

Ratings are normalised against **4.20–4.95**, the band the category actually occupies, because all
23 branches sit between 4.5 and 4.9 and a 0–5 scale would flatten every real difference to noise.

The thresholds come from a **stated posture**, not from a tidy-looking result: they sit at the
tertiles of the portfolio's own observed distribution — *the top third on both axes is worth
defending; the bottom sixth on strength is a candidate for exit.* Earlier values produced
20 HOLD / 2 SHRINK / 1 PROTECT, and a recommendation almost everyone receives is not a
recommendation. **Every number above lives in [`pipeline/config.py`](pipeline/config.py)**; nothing
is hard-coded elsewhere, and the **How** tab renders whatever is in there.

---

## Data: what is real and what is not

A live deployment would read revenue per chair, booking density and lease cost from the chain's own
systems. None of that is public, so every signal here is a public proxy — each tagged with its
provenance and rendered next to the number in the UI, so a reviewer never has to guess.

| Tier | Fields | Source |
|---|---|---|
| **real** | branch names, addresses, **rating and review count** | Bedashing's public listing + public Google rating aggregates |
| **real** | branch coordinates | OSM Nominatim; two coarse results overridden by hand and flagged |
| **real** | 1,354 competitors: existence, name, location, category | OSM via Overpass |
| **real** | 37,137 built-form features behind the demand proxy | OSM, streamed from a Geofabrik extract |
| **derived** | catchments, overlap areas, saturation, coverage gap, demand index | `pipeline/geo/` |
| **synthetic** | competitor **ratings**, review **momentum**, chair **utilisation** | seeded draws from stated priors |

Every synthetic field is a pure function of `RANDOM_SEED` and the record id, so the dataset is
reproducible and nothing shifts under a demo. CI rebuilds it on every commit and fails if it is not
byte-identical to what is committed.

---

## Geographic reasoning

- **Catchments** are radii that vary by urban context — 2.5 km dense urban, 4 km suburban, 6 km low
  density. A salon visit is a planned trip and UAE customers drive, so the radius is wider than a
  European high-street equivalent and tighter where the local pool is already large.
- **Self-overlap** is the real pairwise intersection geometry. The per-branch index takes the
  **union** of sibling intersections, not their sum — summing is the classic error and would push
  any cluster of three into a false `SHRINK`.
- **Saturation** is rivals per catchment km², capped at p90 so one hyper-dense catchment cannot
  compress every other branch to the floor. **Coverage gap** is distance to our nearest lounge
  normalised **by that lounge's own radius**, so it means "under-served" rather than "far".
- **Whitespace** is an H3 res-7 grid (~5 km²/cell) over Dubai, Abu Dhabi and Sharjah. A covered cell
  is **damped to 35%, not deleted**, so the map explains its own gaps.

---

## The AI layer

**Grounded notes — pre-generated, always visible.** Each scored record's *contribution breakdown* is
fed to the model, which returns the sentence an analyst would say in a review: it is given only the
breakdown and instructed to turn arithmetic into an argument, never to supply a fact. 101 notes are
committed, so the AI layer works with no key, and each is stamped with a hash of the payload it came
from — a note whose numbers have since moved renders **stale** rather than passing as current.

**Conversational analyst — live, tool-calling.** [`web/functions/api/chat.js`](web/functions/api/chat.js)
runs a bounded loop over the same static JSON: `network_summary`, `list_branches`, `get_branch`,
`compare_branches`, `find_overlaps`, `top_whitespace`. The prompt forbids answering from memory, and
**the trace of every tool call is returned with the answer and shown in the UI** — you can check it
looked the numbers up rather than recalled them.

Grounding is not only about the numbers being real. An early version answered *"which branches are
most at risk?"* with each branch's market score — every figure correct, the stated *reason* wrong,
because four of the five were flagged on weak **strength**. The fix belonged in the tool contract,
not the prompt: `list_branches` now carries each row's firing `decision_rule`.

**No RAG, on purpose.** 23 branches and ~1k scored cells, fully structured. Every question a
portfolio team asks is a filter, a sort or a join. Function calling answers those exactly and
auditably; a vector store would be fuzzier, unauditable, and simply *unable* to answer "rank these by
overlap share".

---

## Where to be careful

**Trust the geometry** — overlap areas, distances and competitor counts come from real coordinates.
**Question the weights** — they are a stated judgement, which is why they sit in one file and why the
UI prints the rule that fired.

| | |
|---|---|
| **Catchments are radii, not drive times** | An isochrone is the faithful version. The UAE's grade-separated grid narrows the gap, but a lounge behind a creek is over-credited. First upgrade I would make. |
| **Competitor ratings are simulated** | OSM has real rival *locations* but no ratings. The rival **count** is real; the quality comparison is illustrative. |
| **Demand is a built-form proxy** | Residential, retail and premium-venue density — not census. Deliberate: a labour camp and a villa district have similar population density and wildly different spend on a premium blow-dry. |
| **Momentum and utilisation are simulated** | They mark where an operational feed attaches, not what to decide today. Flagged `synthetic` in the UI. |
| **No revenue data at all** | Review volume is the scale proxy. Two of the six `SHRINK` branches are top-ten by volume, so the model is not quietly flagging the small ones — but this is the highest-value addition the chain could make, and it is one CSV column. |

---

## Architecture

```
Python pipeline (offline, once)          committed static files            product
──────────────────────────────           ──────────────────────            ───────
sourcing/  real branches, OSM      ─┐
geo/       catchments, overlap,     ├──►  data/processed/*.json  ──►  React + MapLibre
           saturation, H3 grid      │     ├─ branches.json            (Cloudflare Pages)
scoring/   weighted model +         │     ├─ catchments.geojson
           signed contributions    ─┘     ├─ overlaps.geojson              │
ai/notes   grounded notes (OpenAI)  ──►   ├─ competitors.geojson           │
                                          ├─ whitespace.geojson            ▼
                                          └─ model_card.json        /api/chat function
                                                                    (tool-calling, key
                                                                     server-side only)
```

**Why static.** The dataset changes when a lease changes, not when a page loads. A reviewer clones
the repo and sees the finished product with no database, no keys and no build step beyond
`npm install`.

**Deployment.** A push to `main` runs CI (pipeline · web · dataset); `deploy.yml` fires only on
`workflow_run.conclusion == success`, so a failing test or a drifted dataset stops the release. The
job then reads the canonical deployment back from the Cloudflare API and fails unless production
actually moved — a preview deploy goes green while shipping nothing, which is indistinguishable from
success at a glance. `OPENAI_API_KEY` is **not** a GitHub secret: the endpoint reads it at request
time from the Pages environment, so it never enters the build, the bundle or this repo.

---

## Deeper reading

- **[docs/walkthrough.md](docs/walkthrough.md)** — the demo, in five minutes of reading.
- **[docs/decisions.md](docs/decisions.md)** — 13 decisions, each with the alternative it beat and
  why: radius vs isochrone, union vs sum, function calling vs RAG, thresholds from a posture.
- **[pipeline/config.py](pipeline/config.py)** — every weight and threshold in the product.

**Declared simplifications:** radius catchments over isochrones · public proxies over private
revenue data · three simulated fields · built-form demand over a population raster · function calling
over RAG · committed JSON over a database · Cloudflare over AWS · no auth or real-time refresh.
