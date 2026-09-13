# What to say, slide by slide

Every line here is also inside the deck — press **N** during the presentation to show it under the
slide. Short sentences on purpose: they are easier to say out loud than to read.

*Italic lines are notes to myself, not things to say.*

**Timing:** slides 1–7 about 12 minutes · the live demo 10–12 · slides 9–15 about 10 · then questions.
If the slot is short, cut slides 4 and 14 and shorten the demo to three clicks.

---

## 1 · Which shops do we protect, hold, or shrink?

Bedashing is a beauty salon chain in the UAE. They have twenty-three shops.

Every year someone has to decide: which shops do we keep, which do we grow, and which do we close.

I built a tool that makes that decision — and explains it. It is online right now. You can open it
while I talk.

*Do not say React, Python or OpenAI yet. The brief says this is not a coding test.*

---

## 2 · One person. Three decisions.

The tool is for one person. The Head of Retail Portfolio. This is the person who signs the rent
contract.

The brief said "leadership". But a tool for everybody is a tool for nobody. So I picked one person.

This person makes three decisions. Protect, hold or shrink each shop. And where to open the next one.

*If they ask about the job title: "That title is my assumption. What matters is the role — whoever
owns the profit and loss of the shops. If at Bedashing that is the COO, nothing in the tool changes."*

---

## 3 · What it found

This is what the tool found. Two shops to protect. Fifteen to hold. Six to shrink.

Now look at one of them. Ministry Area, in Abu Dhabi.

Sixty-five per cent of its area is already covered by two of our own shops.

**And Ministry Area is not a weak shop. It is the fifth best out of twenty-three.**

So the problem is not the shop. The problem is that we are paying rent twice for the same customer.

*Say the number, then stop for two seconds. The contradiction is what makes them listen.*

---

## 4 · We already cover our own ground

This is Abu Dhabi. Every circle is the area one shop serves.

The red parts are where our own circles cover the same ground.

Look at these two. Khalifa City and West Yas. They share twenty square kilometres.

**But it is not equal.** Khalifa City loses forty per cent of its area. West Yas loses only eighteen.

So if we have to choose one, we already know which one.

*This is the slide that makes "overlap" feel real. Do not rush it.*

---

## 5 · Strong shop. Weak ground.

Now all twenty-three shops, on two axes.

Left to right: how good is the shop. Bottom to top: how good is the ground.

Ministry Area is here. Far right — so it is a strong shop. Very low — so the ground is bad.

**If I used one single score, this shop would be number five, and I would never look at it again.**

*Also point out: the red dots are not all on the left. That answers "are you just closing the small
ones?" before they ask it.*

---

## 6 · One signal

How does the tool get these numbers? Here is the simplest example.

This shop has four point eight stars.

All our shops are between four point five and four point nine. So if I score from zero to five, every
shop looks the same. The differences disappear.

Instead I score inside the real range: four point two to four point nine five. Four point eight sits
eighty per cent up that range.

Then I multiply by the weight of this signal — thirty per cent. So this signal adds zero point two four.

**That is all. There is no second step.**

---

## 7 · One axis

Same arithmetic, now for the whole second axis. Three numbers.

Demand in the area: plus zero point one seven seven.

Room against competitors: plus zero point two two six.

And the overlap with our own shops: **minus** zero point one two nine.

Add them: zero point two seven three.

The rule says: if the market score is below zero point four, and the overlap is above forty-five per
cent, then shrink. Both are true. So: shrink.

**And notice: the three numbers add up to the score exactly. The explanation is not a story about the
model. It is the model.**

---

## 8 · Live demo

*Switch to the browser. Leave the slide behind you so you can see the list if you lose your place.*

1. **The red areas** — where we compete with ourselves. *(2 min)*
2. **One shop, and why** — the rule, printed on screen. *(3 min)*
3. **All 23 on one chart** — strong shops on bad ground. *(1 min)*
4. **Where to open next** — 573 areas, scored. *(2 min)*
5. **Ask the assistant** — then open the tool trace. *(3 min)*

*If you are short on time, cut number four. One, two and five carry the argument.*

*On number five, open the tool trace. For an AI role this is the most important thing you show all
day: it proves the answer was looked up, not remembered.*

---

## 9 · Two jobs. Both checkable.

There are two AI parts in this.

First: every shop has a short written summary. The model only receives the numbers you just saw. It
has one instruction — explain the numbers, never invent a fact.

Second: you can ask questions in normal English. And under every answer, you can open the tool trace
and see exactly which data it asked for.

**So you can check that it looked the number up. It did not remember it.**

*If they ask "how do you stop it inventing things?" — this slide is the answer. Point at the trace.*

---

## 10 · Every number says where it came from

A real version of this would use the company's own data: revenue per chair, bookings, rent.

That data is not public. So I used public data — and I labelled every single field.

Green is real. Blue is calculated by me from real data. Purple is simulated.

You never have to guess whether a number on the screen is a measurement or a simulation.

**And this is the important part: the value of this project is not where the data comes from. It is
what happens to the data. Connect the real booking system and the same pipeline gives real answers.**

---

## 11 · Four decisions

The brief says the hardest part of real work is not coding. It is deciding what to simplify and what
to trust. So here are four decisions.

**One. No machine learning.** Nobody has ever labelled which shops should have closed. So there is
nothing to learn from. And twenty-three rows is far too little data. Also — a rent decision gets
challenged in a meeting, and "the model said so" is not an answer.

**Two. The real shared shape, not adding overlaps up.** If three shops sit close together, they all
cover the same piece of ground. If I add the overlaps, I count that ground three times — I can even
get more than one hundred per cent. So I take the real shape of the shared area instead. This changed
real results.

**Three. Buildings, not population.** A workers' housing area and a rich neighbourhood can have the
same number of people, and completely different spending on an expensive haircut. So I count what is
built, not who lives there.

**Four. Files, not a database.** This data changes when a rent contract changes, not when a page
loads. So you can download the project and run it with no keys and no server.

---

## 12 · Trust the geometry. Question the weights.

Two sentences.

**Trust the geometry.** The distances, the areas, the number of competitors — all of that is measured
from real coordinates. It is correct.

**Question the weights.** Thirty per cent for rating, forty-five per cent for demand — I chose those
numbers. That is a management opinion, not a fact.

So I put them all in one file. And the tool always prints the rule it used.

**If you disagree with a result, we have a conversation about weights. You are not arguing with a
black box.**

*If they ask what you would fix first, say it with no hesitation: real driving time instead of circles.*

---

## 13 · AI wrote the code. I decided what it should be.

I used an AI agent to write most of this code. The brief expects that — it says so directly.

So the interesting question is not whether I used AI. It is what I kept control of.

I decided who the user is. I decided the model. I decided what to trust and what to simplify.

And I wrote the tests — because tests are what catch the agent when it is wrong.

**Three hundred and thirteen tests. Ninety-eight per cent coverage. They found six real bugs.**

One more thing: the data rebuilds exactly the same every time, and the build fails if it does not. So
nothing moves under a demo.

---

## 14 · Three steps

Three next steps, in order.

**One. Revenue.** One column in one file. Today I use review count as a stand-in for size. Revenue
would replace the weakest part of the model, and it would turn "which shops are at risk" into "how
much money is at risk". Cheapest change, biggest effect.

**Two. Real driving time** instead of circles. A circle does not know about a bridge or a creek.

**Three. The same pipeline for other companies.** Nothing here is about beauty salons. Change the
list of shops and it works for any chain.

---

## 15 · Close

One sentence to finish.

A portfolio team can now point at any shop and see the exact numbers that judged it.

And the first thing the tool found was that our biggest competitor in Abu Dhabi is us.

*Then stop talking. If nobody speaks: "I am happy to go deeper on the geography, the scoring, the AI
part or the deployment — whichever is most useful."*

---

# Appendix — only if they ask

## 17 · Architecture

All the heavy work happens once, before anyone opens the page. The Python part reads the data, builds
the areas, finds the overlaps, scores everything, and writes normal files. The website just reads
those files — so you can download the project and run it with no keys and no database. The only
server code is one small function that talks to OpenAI, so the API key never reaches the browser.

## 18 · Three traps

Three places where the obvious way to build it is quietly wrong.

One. If three shops sit together they all cover the same ground. Adding the overlaps counts it three
times.

Two. One very crowded area would squash every other shop to the bottom of the scale. So I cut the
scale at the ninetieth percentile.

Three. Three kilometres from a city shop is a real gap. Three kilometres from a countryside shop is
already covered. So I divide by that shop's own radius.

And the desert problem: empty desert scores beautifully on "nobody covers this". So any area below a
minimum demand is skipped, whatever it scores.

## 19 · Where the limits came from

My first version gave twenty hold, two shrink, one protect. A recommendation that almost everybody
receives is not a recommendation.

So I wrote down the management position first: the top third on both axes is worth defending, the
bottom sixth is a candidate to exit. Then I put the limits at the thirds of the real distribution.

The two, fifteen, six result is the **consequence** of that position — not the target.

## 20 · Right numbers. Wrong reason.

I asked it: which branches are most at risk. Every number in the answer was correct. But the
**reason** was wrong — it looked at whichever number was low and made up a story around it.

The model was not the problem. The tool was. The tool gave it scores, but not the rule that actually
fired. So it did what any careful person would do with that data.

I added the rule to the tool output. Now it answers the same question in one call and quotes the
exact limit.

**Grounding is usually a data problem, not a prompt problem.**

## 21 · Why no vector search

The data is twenty-three shops and about a thousand scored areas, and it is fully structured — rows
and columns.

Every real question is a filter or a sort. "Which shops are at risk." "Where do we overlap most."
"Best area in Dubai."

Function calling answers those exactly, and shows its work. A vector search would be approximate,
impossible to check, and it simply cannot sort by a column.

**Not using the fashionable tool was the decision. It is not a gap.**

## 23 · What they will ask

- **"Are you just closing the small shops?"** No. Two of the six are number **6 and 9 of 23** by
  size. They are flagged on 65% and 61% overlap, not on performance.
- **"Why not machine learning?"** Nothing to learn from — nobody labelled which shops should have
  closed. And 23 rows is too little data.
- **"How do you know the AI is not inventing?"** Every answer shows the tools it called. The
  summaries only receive the numbers, and are told never to add a fact.
- **"Some data is simulated."** Three fields, all labelled. Locations, ratings, competitors and
  buildings are real.
- **"How long with real data?"** The pipeline takes one CSV. The work is agreeing the weights with
  the business.
