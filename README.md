# Bedashing Network Intelligence

[![CI](https://github.com/clarriu97/2pz/actions/workflows/ci.yml/badge.svg)](https://github.com/clarriu97/2pz/actions/workflows/ci.yml)
![pipeline coverage](https://img.shields.io/badge/pipeline%20coverage-98%25-brightgreen)
![web coverage](https://img.shields.io/badge/web%20coverage-98%25-brightgreen)

**AI-enabled geospatial decision support for retail network right-sizing.**

A decision-support tool for the **Head of Retail Portfolio** at [Bedashing Beauty
Lounge](https://bedashingbeauty.com), a premium UAE salon and wellness chain with 23 lounges. It
answers three questions a portfolio review actually has to settle:

1. **Which lounges are earning their footprint?** → `PROTECT` / `HOLD` / `SHRINK` per branch.
2. **Where are we paying rent twice for the same customer?** → self-overlap between our own catchments.
3. **Where is there demand we do not reach?** → `GROW` / `WATCH` / `SKIP` per candidate zone.

Every recommendation carries the **signed contribution of each signal that produced it**, summing
exactly to the score. A conversational analyst answers questions by calling tools over the same
data the map renders.

---

## Run it

The product is static. All scoring happens offline in a Python pipeline whose output is committed,
so **no API key is needed to see the whole thing**:

```bash
cd web && npm install && npm run dev
```

Open the printed URL. That is the complete product except the live chat.

### The live analyst (optional)

Only the conversational analyst needs a key, because it proxies OpenAI. The pre-generated analyst
notes on every branch and zone are committed and visible without one.

```bash
cd web
cp .dev.vars.example .dev.vars    # then put your OPENAI_API_KEY in it
npm run build
npx wrangler pages dev dist       # serves the app AND functions/api/chat.js
```

### Re-running the data pipeline (optional)

```bash
uv sync
uv run python -m pipeline.run              # rebuild from committed caches — no network, no keys
uv run python -m pipeline.run --offline    # same, but a cache miss is an error (what CI runs)
uv run python -m pipeline.run --refresh    # re-fetch Nominatim + Overpass (slow; public rate limits)
uv run python -m pipeline.run --notes      # also regenerate the AI notes (needs OPENAI_API_KEY)
```

Every remote response is cached under `data/raw/` and committed, so the default invocation is fully
offline and reproduces the committed dataset byte for byte. CI asserts exactly that.

---

## Tests, linting and CI

Every push and pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml), which
fails on any formatting, linting, typechecking, test or **coverage** regression. Three independent
jobs:

| Job | What it runs | Gate |
|---|---|---|
| **pipeline** | `ruff format --check` · `ruff check` · `pytest` | **299 tests**, coverage must stay **≥ 95%** (`--cov-fail-under` in [`pyproject.toml`](pyproject.toml)) |
| **web** | `prettier --check` · `oxlint` · `tsc` · `vitest run --coverage` · `vite build` | **176 tests**, coverage must stay **≥ 85%** lines / **80%** branches (thresholds in [`web/vite.config.ts`](web/vite.config.ts)) |
| **dataset** | `pipeline.run --offline` then `git diff` | the committed dataset must be reproducible **byte for byte** with no network |

Current coverage — **97.80%** lines on the pipeline, **97.83%** statements on the web app. Both
jobs write a coverage table into the GitHub Actions **run summary** and upload the full report as
an artifact, so the numbers are visible on every run rather than only in a badge.

Run the same gates locally:

```bash
uv sync && uv run ruff format --check . && uv run ruff check . && uv run pytest
```

```bash
cd web && npm ci && npm run check
```

### What the tests actually assert

They are not shape tests. Each one guards a claim the product makes to a reviewer:

- **The explainability invariant.** `AxisScore` refuses to exist if its signed contributions do not
  sum to its score. That is the whole basis of the "why" panel, so it is enforced by a validator
  rather than trusted — and there is a test that the validator rejects a score the breakdown cannot
  explain.
- **Signal direction.** Better ratings, more reviews and a stronger local position must each *raise*
  the strength score; saturation and self-overlap must *lower* the market score. If a sign ever
  flipped, every explanation in the product would still add up correctly while being a lie.
- **Threshold boundaries.** `PROTECT` at exactly `STRENGTH_HIGH`, `HOLD` one epsilon below. An
  off-by-one there silently reclassifies a lease.
- **The union-not-sum guarantee.** Four lounges stacked on the same spot must produce a
  cannibalisation share ≤ 1.0, and strictly less than the naive sum of their pairwise overlaps.
- **The demand floor.** Empty desert scores beautifully on "coverage gap"; a test pins that it can
  never surface as an opportunity.
- **Grounding.** The note payload is asserted to contain no field the model could hallucinate
  revenue or rent from, and the chat tools are asserted to return the contribution breakdown with
  every score.
- **Reproducibility.** A full pipeline run with the network stubbed produces byte-identical output
  twice, and CI proves the committed dataset is what the committed code produces.

Four real bugs were found by writing these, each of which would have shipped silently: unclosed
H3 GeoJSON rings (invalid GeoJSON that some renderers drop), a percentile index that floored to
zero and collapsed the saturation signal to a constant 0.5 for every branch, non-unique Overpass
cluster keys that discarded a whole cluster's competitors, and an extract reader that lost every
way sharing a first node with another — which is most adjacent buildings.

### Tooling

| Concern | Python | Web |
|---|---|---|
| Formatting | `ruff format` | `prettier` |
| Linting | `ruff check` (E, W, F, I, UP, B, C4, SIM, RUF) | `oxlint` (correctness, suspicious, perf + react/typescript/unicorn) |
| Types | Pydantic models validate at every boundary | `tsc --noEmit`, strict |
| Tests | `pytest` + `pytest-cov` | `vitest` + `@testing-library/react` + `@vitest/coverage-v8` |
| Dev deps | `[dependency-groups] dev` in `pyproject.toml` | `devDependencies` in `web/package.json` |

All data modelling goes through **Pydantic** ([`pipeline/models.py`](pipeline/models.py)) rather
than dicts or dataclasses. These shapes are a contract between the Python pipeline, the React app
and the chat endpoint's tools; `extra="forbid"` means a renamed field fails inside the pipeline
where the traceback points at the cause, instead of surfacing as `undefined` in a map layer or as
a confidently wrong answer from the analyst.

---

## What you are looking at

Five toggleable map layers, one per functional block, plus a side panel with five tabs.

| Layer | What it shows |
|---|---|
| **Branch network** | 23 lounges. Circle size = review volume (our scale proxy), colour = recommendation. |
| **Catchments** | Service area per lounge, 2.5–6 km by urban context. |
| **Self-overlap** | The actual intersection polygons where our own catchments compete. |
| **Competition** | 1,354 real salons, spas and hairdressers from OpenStreetMap. |
| **Whitespace grid** | 573 H3 cells across Dubai, Abu Dhabi and Sharjah, scored for growth. |

| Tab | What it answers |
|---|---|
| **Why** | The full contribution breakdown for whatever is selected, plus its AI note and its caveats. |
| **Compare** | A sortable table of all 23 branches on every scored signal. |
| **Growth** | The whitespace shortlist, ranked. |
| **Analyst** | Natural-language Q&A with a visible tool trace. |
| **How** | Business framing, provenance of every field, the model's weights, and where not to trust it. |

**Start here:** open **How** and read the framing, then turn on *Self-overlap*, click the largest
red wedge in Abu Dhabi, and follow it into the two branches it belongs to. That path shows the
geographic reasoning, the decision logic and the explainability in about ninety seconds.

### What it currently concludes

The portfolio splits **2 PROTECT · 15 HOLD · 6 SHRINK**, and
**17 of 573** scored cells come out `GROW`.

The headline finding is a real fact about the real network, not an artefact of the model:
**Ministry Area shares 65% of its catchment with two of our own lounges, and Al Maqta 61%.** Both
are individually *strong* branches — Ministry Area scores 0.71 on strength, well above the
portfolio median — and both are flagged `SHRINK` purely because our own network already covers
their ground. That is a consolidation decision, not a performance problem, and it is exactly the
distinction the two-axis matrix exists to make. A single-score ranking would have buried it.

---

## Data: what is real and what is not

The chain is real, the geography is real, and most of the signal is real. A live deployment would
read revenue per chair, booking density, staff utilisation and lease cost from the chain's own
systems. None of that is public. So each field is tagged with its provenance and the UI renders the
tag next to the number — a reviewer never has to guess whether they are looking at a fact.

| Tier | Fields | Source |
|---|---|---|
| **real** | branch names, areas, addresses, **Google rating and review count** | Bedashing's public location listing, cross-referenced with public Google Maps rating aggregates (`data/raw/branches_seed.csv`, committed) |
| **real** | branch coordinates | OpenStreetMap Nominatim geocoding; two coarse results overridden by hand and flagged (`data/raw/branch_coords_override.json`) |
| **real** | competitor existence, name, location, category | OpenStreetMap via Overpass (`shop=beauty\|hairdresser\|massage`, `leisure=spa`, `amenity=spa`) |
| **real** | zone built-form counts | OpenStreetMap: **37,137 features** — residential buildings, everyday retail and services, premium venues — streamed from a Geofabrik extract |
| **derived** | catchments, overlap areas, saturation, coverage gaps, demand index | computed by `pipeline/geo/` from the real inputs above |
| **synthetic** | **competitor ratings**, branch review **momentum**, **chair utilisation** | seeded draws from stated priors — see the caveats below |

Synthetic fields are pure functions of `config.RANDOM_SEED` and the record id, so the dataset is
reproducible and nothing shifts under a demo.

---

## The decision model

A two-axis matrix, not machine learning. **Deliberately.** A portfolio committee has to defend a
lease decision to a CFO, and "the gradient boosting said so" is not a defence. Because every score
is a weighted sum of normalised signals, the explanation is not a post-hoc approximation of the
model — it *is* the model.

### Existing branches

**X — branch strength**: how well this lounge performs as a business.

| Signal | Weight | What it is |
|---|---|---|
| `rating_norm` | +0.30 | Google rating, normalised against the 4.20–4.95 band the category actually occupies (normalising against 0–5 would flatten every real difference to noise) |
| `review_volume_norm` | +0.25 | log review count — a proxy for footfall, which we do not have |
| `momentum` | +0.20 | recent-review trend vs the branch's own history *(simulated)* |
| `competitive_position` | +0.25 | our rating minus the local rival mean *(rival ratings simulated)* |

**Y — market attractiveness & defensibility**: is the ground worth holding?

| Signal | Weight | What it is |
|---|---|---|
| `demand_norm` | +0.45 | built-form demand proxy for the catchment |
| `headroom_norm` | +0.35 | 1 − competitive saturation |
| `cannibalisation_penalty` | **−0.20** | share of our catchment also covered by our own lounges |

**Label mapping** — the rule that fired is printed verbatim in the UI for every branch:

- `PROTECT` — strength ≥ 0.65 **and** market ≥ 0.47.
- `SHRINK` — strength < 0.51, **or** (market < 0.40 **and** self-overlap ≥ 45%). The second clause
  is the "we are competing with ourselves" exit: a branch can be individually strong and still be
  the wrong branch to keep.
- `HOLD` — everything else.

Those four numbers are set by a **stated posture**, not picked to look tidy: they sit at the
tertiles of the portfolio's own observed distribution on each axis — *the top third on both axes is
worth defending; the bottom sixth on strength is a candidate for exit.* The earlier values produced
20 HOLD / 2 SHRINK / 1 PROTECT, and a recommendation almost everyone receives is not a
recommendation. Disagreeing with the posture is a four-number change in one file.

### Whitespace zones

`opportunity = 0.45·demand + 0.35·coverage_gap − 0.20·saturation`, then:

- a zone already inside one of our catchments is **damped to 35%**, not deleted — the map still
  shows why it was passed over;
- a zone below a demand floor of 0.12 is `SKIP` regardless of score, because empty desert scores
  beautifully on "coverage gap" and must never surface as an opportunity;
- `GROW` ≥ 0.62, `WATCH` ≥ 0.45, else `SKIP`.

**Every number above lives in one file: [`pipeline/config.py`](pipeline/config.py).** Nothing is
hard-coded anywhere else, and `data/processed/model_card.json` stamps the exact parameterisation
that produced the committed dataset, which is what the **How** tab renders. Re-tuning the
portfolio's risk appetite is a one-file change.

---

## Geographic reasoning

- **Catchments** are haversine radii that **vary by urban context** — 2.5 km dense urban, 4 km
  suburban, 6 km low density. A salon visit is a planned, discretionary trip and UAE customers
  drive, so the catchment is wider than a European high-street equivalent; dense mixed-use
  districts get a tighter radius because the local pool is larger and rivals are closer.
- **Self-overlap** is the pairwise intersection of our own catchments, computed in a locally-flat
  planar frame. The per-branch cannibalisation index takes the **union** of sibling intersections,
  not their sum — summing is the classic error, and would push any cluster of three to a false
  `SHRINK`.
- **Saturation** is competitors per catchment km², normalised against the portfolio's own
  distribution and capped at the 90th percentile, so one hyper-dense catchment does not compress
  every other branch to the bottom of the scale.
- **Coverage gap** is distance to our nearest lounge normalised **by that lounge's own radius**, so
  3 km from a dense-urban branch is a genuine gap while 3 km from a low-density branch is already
  served. That normalisation is what makes the signal mean "under-served" rather than "far".
- **Whitespace grid** is H3 resolution 7 (~5 km² per cell, ~one neighbourhood) across the three
  metros where we have enough presence for the comparison to mean anything.

---

## The AI layer

Two uses, both chosen because they do work a weighted sum cannot.

**1. Grounded analyst notes — pre-generated, always visible.**
`pipeline/ai/notes.py` feeds each branch's and zone's *contribution breakdown* to the model and gets
back the sentence an analyst would say in a review meeting. The model is given only the scored
record — the signals, weights and signed contributions — and is instructed to translate arithmetic
into an argument, never to supply a fact. Notes are committed to `data/processed/`, so the AI layer
works with **no key**, and nothing changes under us mid-demo. Each note is stamped with a hash of
the payload it came from; a note whose payload has since changed is shown as **stale** rather than
passed off as current.

**2. Conversational analyst — live, tool-calling.**
`web/functions/api/chat.js` runs a bounded tool-calling loop over the same static JSON:
`network_summary`, `list_branches`, `get_branch`, `compare_branches`, `find_overlaps`,
`top_whitespace`. The system prompt forbids answering portfolio questions from memory, and **the
trace of every tool call is returned with the answer and shown in the UI**, so you can check the
analyst looked the numbers up rather than recalled them.

### No RAG, no embeddings — on purpose

The dataset is 23 branches and ~1k scored cells, fully structured. Every question a portfolio team
asks is a filter, a sort or a join: *"which branches are most at risk"*, *"where do we overlap
most"*, *"best whitespace in Dubai"*. Function calling answers those exactly and auditably. A vector
store would be fuzzier, unauditable, and simply **unable** to answer *"rank these by overlap
share"* at all. Choosing not to reach for embeddings is the judgement call, not a gap.

---

## Where to trust this, and where to be careful

This section is the honest one. It is also rendered in the **How** tab, because a reviewer reads
what is on screen.

**Trust the geometry.** Overlap areas, distances, competitor counts and coverage gaps are computed
from real coordinates and real OSM features. They are as good as their inputs and the arithmetic is
not in doubt.

**Question the weights.** The numbers that turn geometry into a label are a stated management
judgement, not an estimate from data. That is precisely why they sit in one editable file and why
the UI shows the rule that fired. Disagreeing with a label should be a conversation about weights,
which is a conversation a portfolio team can actually have.

**Specific limitations:**

- **Catchments are radii, not drive times.** A 10-minute isochrone is the faithful version. The UAE's
  grade-separated grid makes the gap smaller than it would be in a European city, but a lounge
  behind a creek or a single bridge is over-credited. This is the first upgrade I would make, via
  OpenRouteService or OSRM.
- **Competitor ratings are simulated.** OSM gives real rival *locations* but no ratings, so
  `competitive_position` ("we rate +0.2★ above the local mean") rests on a drawn distribution. The
  rival **count** is real; the rating comparison is illustrative. Swapping in Google Places
  ratings is a change to one module, `pipeline/sourcing/competitors.py`.
- **Demand is a built-form proxy, not a census.** Residential, retail and premium-venue density from
  OSM. I chose this over a population raster deliberately: a labour accommodation block and a villa
  district have similar population density and wildly different spend on a premium blow-dry, so
  population alone would actively mislead here. The cost is that it under-reads brand-new districts
  OSM has not mapped and over-reads tourist strips. Cells with no mapped features are flagged
  `no_osm_features` so "unknown" is not read as "low".
- **Momentum and chair utilisation are simulated.** They are in the model to show where an
  operational feed attaches, not to drive a decision today. Both are flagged `synthetic` in the UI.
- **Sparse-review branches are flagged, not silently scored.** Palm Jumeirah has 38 reviews; its
  4.9★ is statistically thin, and the branch carries a low-confidence caveat saying so.
- **A hex is a search area, not a site.** ~5 km² says which neighbourhood to look in, not where to
  sign a lease.
- **Ratings are a quality signal, not a profit signal.** A lounge can be adored and unprofitable.
  Without revenue data, no model here can tell you that, and I would not pretend otherwise.

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

**Why static files.** The dataset is small and changes when a lease changes, not when a page loads.
Committing the pipeline's output means a reviewer clones the repo and sees the finished product with
no database, no keys and no build step beyond `npm install`. It is also the fallback mode the brief
asks for, built in by default rather than bolted on.

**Why Cloudflare Pages + Functions.** The static app deploys in seconds, and one Pages Function
keeps the OpenAI key off the browser. Zero ops for a case study. Production on AWS would be
S3 + CloudFront for the site, Lambda behind API Gateway for the endpoint, and R2/D1 or
S3 + DynamoDB once the dataset outgrew a JSON file. That is a deployment target, not a redesign.

**Repository layout**

```
pipeline/
  config.py          every weight, threshold, radius — the single tuning surface
  models.py          Pydantic contracts for every record that crosses a boundary
  sourcing/          branches, geocoding, Overpass client, competitors, demand proxy
  geo/               catchments + overlap, saturation, H3 whitespace grid
  scoring/model.py   the decision model and its signed contributions
  ai/                prompt design + offline note generation
  run.py             orchestrates end to end, writes data/processed/
tests/               pytest suite — invariants, geometry, scoring, AI grounding, end to end
data/raw/            committed source caches — re-runs need no network
data/processed/      what the product reads
web/
  src/               React + MapLibre app, with colocated *.test.tsx
  functions/api/     the analyst endpoint and its tool tests
.github/workflows/   ci.yml (every commit) and deploy.yml (main, after CI passes)
docs/decisions.md    the trade-off log
```

---

## Declared simplifications

Each of these was a choice, and each is defended above or in [`docs/decisions.md`](docs/decisions.md).

- Radius catchments instead of drive-time isochrones.
- Public proxies instead of private revenue / footfall / utilisation data.
- Competitor ratings, review momentum and chair utilisation simulated from seeded priors.
- Built-form demand proxy instead of a population raster.
- Function calling over structured JSON instead of RAG.
- Static committed JSON instead of a database.
- Cloudflare Pages + Functions instead of AWS.
- No auth, no multi-tenancy, no real-time refresh — out of scope for the decision this supports.
