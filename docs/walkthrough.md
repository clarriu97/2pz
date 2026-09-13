# Walkthrough

**Live: [2pz.larri.dev](https://2pz.larri.dev)** · no login, no key, nothing to install.

This is the written half of the demo the brief asks for. Ten minutes of reading, or follow it
click by click in the app. Every number below is in the product — nothing here is a claim you have
to take on trust.

---

## What this is

A decision-support tool for the **Head of Retail Portfolio** at Bedashing Beauty Lounge, a premium
UAE salon chain with 23 branches. Not "leadership" in general: the one role that signs a lease,
funds a refit, or lets a site go.

It answers three questions a portfolio review has to settle:

1. Which branches are earning their footprint? → `PROTECT` / `HOLD` / `SHRINK`
2. Where are we paying rent twice for the same customer? → catchment self-overlap
3. Where is there demand we do not reach? → `GROW` / `WATCH` / `SKIP`

**The current answer: 2 PROTECT · 15 HOLD · 6 SHRINK, and 17 of 573 scored cells come out `GROW`.**

---

## The headline

If you read nothing else:

> **Ministry Area shares 65% of its trade area with two of our own lounges. Al Maqta shares 61%.**
> Both score *above the portfolio median* on branch strength — Ministry Area is the fifth strongest
> of the 23. Both are flagged `SHRINK` purely because our own network already covers their ground.

That is a **consolidation decision, not a performance problem**, and it is the distinction the
whole product exists to make. A single "branch health score" would have placed Ministry Area
comfortably mid-table and shown you nothing.

---

## Follow it in the app

### 1 · Start with "How" — 2 min

Open the **How** tab before the map. It names the decision-maker, the decisions, and — the part
worth your attention — **the provenance of every field**.

A real deployment reads revenue per chair, booking density and lease cost from the chain's own
systems. None of that is public, so every signal here is a public proxy, and each is tagged in the
UI as one of:

| Tag | Meaning | Examples |
|---|---|---|
| `real` | sourced from a public dataset | branch ratings and review counts, 1,354 competitor locations, 37,137 built-form features |
| `derived` | computed by the pipeline from real inputs | catchments, overlap areas, saturation, demand index |
| `synthetic` | simulated — the chain does not publish it | competitor ratings, review momentum, chair utilisation |

You never have to guess whether a number on screen is a measurement or a simulation.

### 2 · The network — 2 min

23 branches. **Colour** is the recommendation; **circle size** is review volume, our proxy for
footfall. The dashed ring around each is its catchment: 2.5 km in dense urban districts, 4 km
suburban, 6 km low density — a salon visit is a planned, discretionary trip and UAE customers
drive, so the radius widens where the customer already expects to.

### 3 · Self-overlap — 3 min ⭐

Turn on **Self-overlap**. The red wedges are the *actual intersection geometry* of our own
catchments, not a number in a table.

Click the largest wedge in Abu Dhabi. The panel shows the pair, the shared area in km², and —
the part that carries the decision — **the asymmetric shares**:

> Khalifa City ∩ West Yas · 20.0 km² shared · Khalifa City gives up **40%** of its trade area,
> West Yas **18%**.

Overlap is asymmetric, and the branch surrendering the larger share is the one under pressure. That
asymmetry is what turns "these two are close" into "this is the one to consolidate".

A detail that changes labels: a branch's overlap is the **union** of its siblings' intersections,
not their sum. Three lounges clustered together all overlap the same wedge; summing counts it three
times, can exceed 100%, and would push a healthy cluster into a false `SHRINK`.

### 4 · Why a branch got its label — 5 min ⭐⭐

Click into **Ministry Area**. This is the centre of the product.

**The rule that fired, printed verbatim:**

```
market 0.273 < 0.4 AND self-overlap 65% ≥ 45%
```

You do not have to infer why. It tells you.

**The signed contribution breakdown**, sorted by impact:

```
WHY — BRANCH STRENGTH                                    0.712
  Guest rating            4.8★                    norm 0.80 × w +0.30  = +0.240
  Position vs local rivals +0.38★ vs local mean   norm 0.88 × w +0.25  = +0.220
  Review volume           443 reviews             norm 0.69 × w +0.25  = +0.172
  Recent momentum         −20% vs own trend       norm 0.40 × w +0.20  = +0.080
                                    sum of contributions  0.712
```

**The sum equals the score exactly.** That is not a coincidence and not a post-hoc approximation:
every score is a weighted sum of normalised signals, so the breakdown *is* the model. A Pydantic
validator refuses to construct a score whose contributions do not add up to it.

Click any row to expand the reasoning behind that signal.

```
WHY — MARKET & DEFENSIBILITY                             0.273
  Competitive headroom    17 rivals · 0.87/km²    norm 0.65 × w +0.35  = +0.226
  Catchment demand        39% of metro peak       norm 0.39 × w +0.45  = +0.177
  Self-cannibalisation    65% of catchment shared norm 0.65 × w −0.20  = −0.130
```

Strength 0.71, market 0.27. **Good branch, contested ground.**

**The analyst note**, generated offline from that breakdown and committed to the repo so it needs
no API key:

> *"We recommend shrinking the Bedashing Beautification Spot Ministries Complex due to high
> self-cannibalisation, sharing 65% of its catchment with two nearby lounges, despite strong guest
> ratings and competitive positioning…"*

Every figure in it traces back to the record above. The model is handed the scored record and told
to translate arithmetic into an argument — never to supply a fact.

**"Where to be careful"** closes the panel with this branch's specific caveats, or says plainly
that there are none.

### 5 · The decision matrix — 2 min ⭐

Open **Compare**. The scatter puts all 23 branches on both axes at once, with the thresholds from
`config.py` drawn as lines.

Find Ministry Area: **far right, near the bottom**. Strong branch, weak ground, flagged. In one
glance you can see the SHRINKs are *not* all at the bottom-left — which is the honest answer to
"are you just closing the small ones?"

### 6 · Compare — 2 min

Below the matrix, the sortable table. Sorted ascending by strength so the branches needing a
decision are at the top.

**Click the "Overlap" header.** The order changes completely. Which branch is "worst" depends
entirely on the question: the weakest performer, the most cannibalised and the most competitively
exposed are three different branches, and a portfolio team needs all three views.

### 7 · Growth — 3 min

Turn on **Whitespace** and open the **Growth** tab. H3 hexagons, ~5 km² each, across Dubai, Abu
Dhabi and Sharjah.

```
opportunity = 0.45·demand + 0.35·coverage gap − 0.20·saturation
```

Two rules worth knowing:

- A cell already inside one of our catchments is **damped to 35%, not deleted** — it stays on the
  map with the damping shown as its own line in the breakdown, so the map explains its own gaps. An
  attractive covered cell is a *relocation or capacity* question, not a new site.
- A cell below a **demand floor of 0.12 is `SKIP` regardless of score**. Empty desert scores
  beautifully on "coverage gap", and sand surfacing at the top of a growth shortlist would be the
  most embarrassing failure this product could have.

Click a `GROW` cell to see its breakdown and its distance to the nearest lounge.

### 8 · The analyst — 3 min ⭐

Open the analyst column and ask:

> *"Which branches are most at risk, and why?"*

It answers in one tool call and quotes **the rule that fired** for each branch, with its threshold.
Then expand the **tool trace** underneath the answer:

```
list_branches({"recommendation":"SHRINK","sort_by":"strength","order":"asc"})
  → {"total_matching":6,"branches":[{"branch_id":"BD08",...
```

That trace is the point. It is the difference between an answer that is *grounded* and one that is
merely *fluent* — you can check the analyst looked the numbers up rather than recalling them.

Try also: *"Where are we competing with ourselves the most?"* and *"Compare Khalifa City with Palm
Jumeirah."*

**There is no vector store, deliberately.** 23 branches and ~1,000 scored cells are small and fully
structured; every question a portfolio team asks is a filter, a sort or a join. Function calling
answers those exactly and auditably. Retrieval over embeddings would be fuzzier, unauditable, and
simply unable to answer *"rank these by overlap share"* at all.

---

## How the answers are produced

```
Bedashing public listing + Google rating aggregate ─┐
OpenStreetMap via Overpass (1,354 competitors)      ├─► Python pipeline ─► committed JSON ─► the app
Geofabrik OSM extract (37,137 built-form features) ─┘
```

The pipeline geocodes the branches, builds catchments, intersects them pairwise, counts competitors
per catchment, grids the metros into H3 cells, scores everything, and writes static files.

**Why static?** The dataset changes when a lease changes, not when a page loads. This is a
portfolio report, not an operational dashboard — nothing it reads moves faster than weekly. In
exchange you get a product that a reviewer can clone and run with no keys, and a CI job that
rebuilds the dataset and fails if it is not byte-identical to what is committed.

### The model, in one box

```
X — Branch strength           Y — Market attractiveness & defensibility
  rating              +0.30     catchment demand              +0.45
  log(review volume)  +0.25     competitive headroom          +0.35
  momentum            +0.20     self-cannibalisation          −0.20
  position vs rivals  +0.25

PROTECT   strength ≥ 0.65 AND market ≥ 0.47
SHRINK    strength < 0.51 OR (market < 0.40 AND overlap ≥ 45%)
HOLD      everything else
```

Two things about those numbers.

**Ratings are normalised against a 4.20–4.95 band, not 0–5.** All 23 branches sit between 4.5 and
4.9; against the full scale every real difference would flatten into noise.

**The thresholds sit at the tertiles of the portfolio's own observed distribution** — *the top
third on both axes is worth defending; the bottom sixth on strength is a candidate for exit*. That
is a stated management posture, and the 2/15/6 split is its consequence rather than its target. The
earlier values produced 20 HOLD / 2 SHRINK / 1 PROTECT, and a recommendation almost everyone
receives is not a recommendation. Every one of these numbers lives in
[`pipeline/config.py`](../pipeline/config.py); change four of them and the product, including the
panel that explains it, follows.

**It is not machine learning, on purpose.** Nobody has labelled which of the 23 branches *should*
be shrunk, so supervised learning has nothing to fit and an ensemble on 23 rows would overfit. More
to the point, a lease decision gets challenged in committee, and "the gradient boosting said so" is
not a defence.

---

## Where to be careful

**Trust the geometry.** Overlap areas, distances, competitor counts and coverage gaps come from
real coordinates and real OSM features.

**Question the weights.** They are a stated judgement, not an estimate from data — which is exactly
why they sit in one file and why the UI prints the rule that fired.

| | |
|---|---|
| **Catchments are radii, not drive times** | An isochrone is the faithful version. The UAE's grade-separated grid narrows the gap, but a lounge behind a creek is over-credited. First upgrade I would make. |
| **Competitor ratings are simulated** | OSM has real rival *locations* but no ratings. The rival **count** is real; the quality comparison is illustrative. |
| **Demand is a built-form proxy** | Residential, retail and premium-venue density — not census. Chosen over a population raster deliberately: a labour camp and a villa district have similar population density and wildly different spend on a premium blow-dry. |
| **No revenue data at all** | Review volume is the scale proxy. Note that two of the six `SHRINK` branches are in the top ten by volume — the model is not quietly flagging the small ones. This is the single highest-value addition the chain could make, and it is one CSV column. |

---

## If you want to run it yourself

```bash
cd web && npm install && npm run dev
```

That is the entire product except the live chat, which needs an OpenAI key on the server. The 101
analyst notes are committed, so the AI layer is visible without one.

To rebuild the dataset from the committed source caches — no network, no keys:

```bash
uv sync && uv run python -m pipeline.run
```

- [`README.md`](../README.md) — setup, the model, the architecture
- [`docs/decisions.md`](decisions.md) — 13 decisions, each with the alternative it was chosen over
- [`pipeline/config.py`](../pipeline/config.py) — every weight and threshold in the product
