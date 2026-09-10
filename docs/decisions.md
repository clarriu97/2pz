# Decision log

The case study says the hardest part is rarely coding — it is deciding what to solve first, what
to simplify, what to trust and what to explain. This file is that record: what I chose, what I
chose *against*, and what it would cost to change my mind.

Roughly in the order the decisions had to be made.

---

## 1. Frame the product around one person, not "leadership"

**Chose:** the **Head of Retail Portfolio** as the single decision-maker, and built every screen for
them.

**Against:** a generic "executive dashboard" serving CFO, COO and regional managers at once.

**Why:** those roles need different products. A CFO wants capital exposure by site; a regional
manager wants staffing. Trying to serve all three produces a screen full of charts that answers
nobody's actual next decision. The portfolio head is the one who signs a lease, funds a refit or
lets a site go — which is exactly the `PROTECT` / `HOLD` / `SHRINK` / `GROW` framing the brief
asks for. Naming them narrowed every subsequent choice, including what to leave out.

**Consequence:** no financial roll-up, no staffing view. Both would be additive later; neither is
this decision.

---

## 2. A transparent weighted matrix, not a model

**Chose:** two axes, each a weighted sum of normalised signals, thresholded into a label.

**Against:** gradient boosting, clustering, or any learned scoring.

**Why:** three reasons, in order of weight.

1. **There is no label to learn from.** Nobody has told us which of the 23 branches "should" be
   shrunk. Supervised learning has nothing to fit; unsupervised clustering would produce groups
   that still need a human to name, and would name them less defensibly than a stated rule.
2. **The output has to survive a committee.** A lease decision gets challenged. "Al Maqta scores
   0.41 on market because 61% of its catchment is covered by two of our own lounges" is a
   defensible sentence. A SHAP plot is not the same thing, and a tree ensemble on 23 rows would
   overfit anyway.
3. **The explanation comes free and is exact.** Because the score is `Σ wᵢ·xᵢ`, the contribution
   list *is* the model rather than an approximation of it. The UI can honestly claim the breakdown
   is complete: the contributions sum to the score, and the app displays that sum.

**Consequence:** the weights are a stated management judgement, not an estimate. That is a real
limitation and I have not hidden it — it is why every weight lives in one file and why the UI prints
the rule that fired. Disagreement about a label becomes a conversation about weights, which is a
conversation a portfolio team can actually have.

---

## 3. Real data wherever it was free; simulated only where it genuinely is not

**Chose:** real branches, real ratings, real review counts, real competitor locations, real
built-form counts. Simulated competitor ratings, review momentum and chair utilisation.

**Against (a):** all-synthetic data on real geography, which was the original plan on the grounds
that the value is in the processing, not the source.

**Against (b):** paying for Google Places to get real competitor ratings.

**Why:** the all-synthetic version is defensible in principle but weaker in practice — a reviewer
cannot tell a well-reasoned model from a well-reasoned model *fed numbers that flatter it*. Twenty
minutes of sourcing turned up Bedashing's public location list and public Google rating aggregates
for all 23 branches, and OpenStreetMap has 1,352 genuine competing venues within 5 km of a branch,
free and key-free. That much real data changes the character of the deliverable: the Abu Dhabi
over-coverage finding is a real fact about a real network, not an artefact of a seed.

So the rule became: **simulate only what is genuinely not obtainable, and label every field.** Three
fields are simulated, and each is tagged `synthetic` in the UI next to the number.

**Consequence:** `competitive_position` — our rating minus the local rival mean — is a real
comparison against a simulated baseline, so its *direction* is illustrative. The rival **count** is
real. Fixing this is one module: `pipeline/sourcing/competitors.py` swaps its rating source and the
provenance registry flips to `real`. The seam is deliberate and it is where I would spend the first
API budget.

---

## 4. Radius catchments, varied by urban context

**Chose:** haversine radii of 2.5 / 4 / 6 km, selected per branch by the built form of its district.

**Against (a):** a single fixed radius for all 23 branches.
**Against (b):** drive-time isochrones from OpenRouteService or OSRM.

**Why:** a single radius is the naive version and would have been visibly wrong — a Palm Jumeirah
catchment and an Al Barsha catchment are not the same shape of market. Isochrones are the faithful
version, and I would build them next; they need a routing key, a per-branch request budget and
error handling for a case where they add less than they would in Europe, because the UAE road
network is grid-like and grade-separated so a 10-minute drive is closer to circular than it would be
in London.

Varying the radius by context captures most of the value of an isochrone for none of the cost, and
it makes the *assumption* explicit and tunable rather than buried.

**Consequence:** a lounge behind a creek or reachable by one bridge is over-credited. Named in the
README trust section. `pipeline/geo/catchments.py` has one entry point to replace.

---

## 5. A built-form demand proxy, not a population raster

**Chose:** demand = weighted log density of residential buildings (0.40), everyday retail and
services (0.25) and premium venues — hotels, malls, gyms, private clinics, marinas (0.35), all from
OpenStreetMap.

**Against:** WorldPop or Kontur H3 population for the UAE, which is free and would have been the
conventional choice.

**Why:** population density is the wrong variable for this business and would have misled
confidently. A labour accommodation block and a Jumeirah villa district can have similar population
density and wildly different spend on a premium blow-dry. Affluence at neighbourhood granularity is
not public for the UAE — so rather than use the available number and quietly hope it correlates, I
built a proxy whose components are individually arguable, and weighted premium-venue density highest
precisely because it is the best free discriminator of spending power.

**Consequence:** it under-reads brand-new districts OSM has not finished mapping and over-reads
tourist strips. Cells with no mapped features are flagged `no_osm_features` so the UI can say
"unknown" rather than imply "low". A production version would combine this with the chain's own
customer postcodes, which is the real answer and needs no public data at all.

---

## 6. Union, not sum, for cannibalisation

**Chose:** a branch's cannibalisation index is the area of the **union** of its siblings'
intersections with its own catchment, as a share of that catchment.

**Against:** summing the pairwise overlap shares.

**Why:** this is a small decision that changes labels. Three lounges clustered in Abu Dhabi all
overlap the same wedge of the map. Summing counts that wedge three times, can exceed 100%, and would
push a whole cluster into a false `SHRINK`. It is the most likely place for a plausible-looking
geometric bug to produce a confidently wrong recommendation, so it is computed properly with shapely
and commented in place.

---

## 7. Damp covered zones, do not drop them

**Chose:** a whitespace cell already inside one of our catchments keeps its score, multiplied by
0.35, and stays on the map.

**Against:** filtering covered cells out of the grid entirely.

**Why:** filtering is cleaner code and worse product. A high-demand cell that we already cover is
genuinely interesting — it is a *relocation or capacity* question, not a new-site question — and a
reviewer asking "why isn't Downtown showing as an opportunity?" deserves to see the answer on the
map rather than infer it from an absence. Damping keeps the cell visible with an explicit
`covered_zone_damping` line in its contribution breakdown, so the map explains its own gaps.

The same reasoning drives the demand floor: empty desert scores beautifully on "coverage gap", so
cells below a demand floor are `SKIP` regardless of score, with the rule stated.

---

## 8. Pre-generate the AI notes offline; keep only chat live

**Chose:** notes generated at build time and committed; a single Pages Function for the live
analyst.

**Against:** generating notes in the browser on demand.

**Why:** three things fall out of pre-generating. The AI layer is visible with **no API key**, which
is the fallback mode the brief asks for and is built in rather than bolted on. The notes are
identical every time, so nothing shifts under a live demo. And the cost is bounded and paid once.

**Consequence:** notes go stale if the config or the data changes. Handled rather than ignored: each
note is stamped with a hash of the payload it was generated from, and a note whose payload no longer
matches is rendered as **stale** instead of being passed off as current.

---

## 9. Function calling over the JSON — explicitly not RAG

**Chose:** six typed tools over the static dataset, with the tool trace returned to the UI.

**Against:** embedding the branch and zone records into a vector store and retrieving by similarity.

**Why:** the dataset is 23 branches and ~1k scored cells, fully structured. Every question a
portfolio team asks is a filter, a sort or a join — *"which branches are most at risk"*, *"where do
we overlap most"*, *"best whitespace in Dubai"*. Function calling answers those exactly. A vector
store would answer them approximately, could not answer *"rank these by overlap share"* at all, and
would add an index to keep in sync with the pipeline for no gain.

Reaching for embeddings here would have been pattern-matching on "AI project", not engineering. The
honest test is whether the technique earns its place on this dataset, and it does not.

**Consequence:** the analyst can only answer what the tools expose. That is a feature — it is why
the trace is shown. Questions outside the tools get "here is what is missing and what data would
answer it" rather than a fluent guess, which is the behaviour the system prompt enforces.

---

## 10. Static committed JSON, no database

**Chose:** the pipeline writes JSON; the pipeline's output is committed; the app fetches files.

**Against:** Postgres/PostGIS, or computing scores in the browser.

**Why:** the data changes when a lease changes, not when a page loads. A database would add
infrastructure to review, credentials to manage and a migration story, in exchange for nothing this
product needs. Committing the output also means the reviewer's first command is `npm install` and
the whole thing works — which the brief explicitly asks for and CI verifies by re-running the
pipeline and failing if the committed data is not reproducible.

Computing in the browser was rejected for a different reason: it would put the decision model in
JavaScript, where it is harder to test, and would mean the map, the notes and the chat could each
disagree about a score. One source of truth, computed once.

---

## 11. Cloudflare Pages, not AWS

**Chose:** Cloudflare Pages for the static app, one Pages Function for `/api/chat`, GitHub Actions
for CI.

**Against:** S3 + CloudFront + Lambda.

**Why:** speed and zero ops for a three-day build, on infrastructure already in place. There is no
architectural argument here, only a time one.

**Scale path**, since it is fair to ask: on AWS this is S3 + CloudFront for the site, Lambda behind
API Gateway for the endpoint, and R2/D1 or S3 + DynamoDB once the dataset outgrows a JSON file. If
the network grew to hundreds of branches, the pipeline would become a scheduled job writing to
object storage and the whitespace grid would move to tiled vector output instead of a single
GeoJSON. None of that changes the model or the product; it is a deployment target.

---

## What I would do next, in order

1. **Drive-time isochrones** (OpenRouteService). The single biggest fidelity gain, and it makes the
   overlap geometry meaningfully more honest.
2. **Real competitor ratings** (Google Places). Removes the largest simulated dependency and makes
   `competitive_position` a real signal rather than an illustrative one.
3. **Sensitivity analysis in the UI.** A slider on each weight, showing which labels flip. The
   fastest way to build trust in a judgement-based model is to let the decision-maker see how
   fragile each label is — and it turns "I disagree with this weight" into a two-second experiment.
4. **The chain's own data.** Revenue per chair and booking density would replace three proxies at
   once and change the model from "defensible" to "correct". Everything above is scaffolding for the
   day that feed exists.
