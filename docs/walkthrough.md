# Walkthrough

**Live: [2pz.larri.dev](https://2pz.larri.dev)** — no login, no key, nothing to install.

This is the written half of the demo. Five minutes of reading, or follow it click by click. Every
number here is on screen in the product.

---

## The finding

**The portfolio splits 2 `PROTECT` · 15 `HOLD` · 6 `SHRINK`, and 17 of 573 scored cells are `GROW`.**

> **Ministry Area shares 65% of its trade area with two of our own lounges. Al Maqta shares 61%.**
> Both score *above the portfolio median* on branch strength — Ministry Area is the fifth strongest
> of 23. Both are flagged `SHRINK` purely because our own network already covers their ground.

That is a **consolidation decision, not a performance problem**, and it is the distinction the whole
product exists to make. A single "branch health score" would have put Ministry Area comfortably
mid-table and shown you nothing.

---

## Five things to click

### 1 · Self-overlap — where we compete with ourselves

Turn on the **Self-overlap** layer. The red wedges are the *actual intersection geometry* of our own
catchments, not a number in a table. Click the largest one, in Abu Dhabi:

> Khalifa City ∩ West Yas · **20.0 km² shared** · Khalifa City gives up **40%** of its trade area,
> West Yas only **18%**.

Overlap is asymmetric, and the branch surrendering the larger share is the one under pressure. That
asymmetry turns *"these two are close"* into *"this is the one to consolidate"*.

### 2 · Why a branch got its label ⭐

Click **Ministry Area**. This is the centre of the product. The rule that fired is printed verbatim —
you never have to infer it:

```
market 0.273 < 0.4  AND  self-overlap 65% ≥ 45%   →  SHRINK
```

And the score it refers to is three multiplications and an addition:

```
Catchment demand        39% of metro peak        0.393 × +0.45  =  +0.177
Competitive headroom    17 rivals · 0.87/km²     0.645 × +0.35  =  +0.226
Self-cannibalisation    65% of catchment shared  0.648 × −0.20  =  −0.129
                                                         market =   0.273
```

**The contributions sum to the score exactly.** Not a post-hoc approximation — every score is a
weighted sum, so the breakdown *is* the model, and a Pydantic validator refuses to construct a score
whose parts do not add up to it. Strength does the same and comes out **0.712**: good branch,
contested ground.

Under it, the analyst note, generated offline from that breakdown and committed to the repo:

> *"We recommend shrinking the Bedashing Beautification Spot Ministries Complex due to high
> self-cannibalisation, sharing 65% of its catchment with two nearby lounges, despite strong guest
> ratings and competitive positioning…"*

Every figure in it traces back to the record above. The model is handed the scored record and told to
turn arithmetic into an argument — never to supply a fact.

### 3 · The decision matrix

Open **Compare**. All 23 lounges on both axes at once, with the thresholds drawn as lines. Find
Ministry Area: **far right, near the bottom**. Strong branch, weak ground.

In one glance you can see the `SHRINK`s are *not* all bottom-left — which is the honest answer to
*"are you just closing the small ones?"*

Below it, sort the table by **Overlap**. The order changes completely: the weakest performer, the
most cannibalised and the most competitively exposed are three different branches, and a portfolio
team needs all three views.

### 4 · Growth

Turn on **Whitespace** and open the **Growth** tab — H3 hexagons, ~5 km² each, scored as
`0.45·demand + 0.35·coverage gap − 0.20·saturation`. Two rules worth knowing:

- A cell already inside one of our catchments is **damped to 35%, not deleted** — it stays on the map
  with the damping shown as its own line, so the map explains its own gaps. An attractive covered
  cell is a *relocation* question, not a new site.
- A cell below a **demand floor of 0.12 is `SKIP` regardless of score**. Empty desert scores
  beautifully on "coverage gap", and sand at the top of a growth shortlist would be the most
  embarrassing failure this product could have.

### 5 · The analyst ⭐

Ask it: ***"Which branches are most at risk, and why?"***

It answers in one tool call and quotes **the rule that fired** for each branch, with its threshold.
Then expand the **tool trace** under the answer:

```
list_branches({"recommendation":"SHRINK","sort_by":"strength","order":"asc"})
  → {"total_matching":6,"branches":[{"branch_id":"BD08",...
```

That trace is the point: it is the difference between an answer that is *grounded* and one that is
merely *fluent*. Try also *"Where are we competing with ourselves the most?"*

**There is no vector store, deliberately.** 23 branches and ~1,000 scored cells, fully structured —
every question a portfolio team asks is a filter, a sort or a join. Function calling answers those
exactly and auditably; retrieval over embeddings would be fuzzier, unauditable, and simply unable to
answer *"rank these by overlap share"* at all.

---

## Before you draw conclusions

**Trust the geometry** — overlap areas, distances, competitor counts and coverage gaps come from real
coordinates and real OpenStreetMap features. **Question the weights** — they are a stated management
judgement, not an estimate from data, which is exactly why they live in one file and why the UI
prints the rule that fired.

Three caveats carry real weight: **catchments are radii, not drive times** (first upgrade I would
make); **competitor ratings are simulated** — their *locations* and *count* are real, the quality
comparison is illustrative; and there is **no revenue data at all**, so review volume stands in for
scale. Note that two of the six `SHRINK` branches are top-ten by review volume: the model is not
quietly flagging the small ones.

The **How** tab in the app lists the provenance of every field — `real`, `derived` or `synthetic` —
so nothing on screen can be mistaken for a measurement it is not.

---

Setup, the full model and the architecture are in [`README.md`](../README.md); the thirteen design
decisions and the alternatives they beat are in [`decisions.md`](decisions.md).
