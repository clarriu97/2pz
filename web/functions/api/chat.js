/**
 * The conversational analyst — a Cloudflare Pages Function.
 *
 * Two reasons this endpoint exists at all:
 *   1. the OpenAI key must never reach the browser, and
 *   2. the model must answer from the portfolio data, not from memory.
 *
 * (2) is the design that matters. The function exposes a small set of typed
 * tools over the same static JSON the page is rendering and runs a bounded
 * tool-calling loop. There is no vector store and no embeddings: 23 branches
 * and ~1k scored cells are small, fully structured, and every question a
 * portfolio team asks is a filter, a sort or a join. Retrieval over embeddings
 * would be strictly worse here — fuzzier, unauditable, and unable to answer
 * "rank these by overlap" at all. Choosing not to use it is the point.
 *
 * The trace of every tool call is returned with the answer so the UI can show
 * what was actually looked up.
 */

export const MODEL = "gpt-4.1-mini";
const MAX_ROUNDS = 5; // enough for look-up -> compare -> answer; bounds cost and latency

export const SYSTEM = `You are the Bedashing Network Analyst, an assistant to the Head of Retail \
Portfolio for a premium UAE salon and wellness chain with 23 lounges.

You answer questions about the branch network and growth opportunities by calling the tools \
provided. The tools are your only source of truth about the portfolio.

How to work:
- ALWAYS call a tool before making a claim about a branch, a zone or a number. Never answer \
portfolio questions from memory.
- When you give a recommendation or a score, say what drove it, using the contribution \
breakdown the tools return. The decision-maker needs the reason, not the number.
- Quantify. "Al Maqta shares 61% of its catchment with two sibling lounges" beats "significant \
overlap".
- Refer to branches by name and area, and include the branch id in brackets like (BD12) the \
first time you mention one, so the interface can link it to the map.
- Be honest about the model's limits. Momentum, chair utilisation and competitor ratings are \
simulated; the demand figure is a built-form proxy from OpenStreetMap, not census population; \
catchments are radii, not drive times. If an answer leans on one of those, say so in one short \
clause.
- If a question cannot be answered from the tools, say what is missing and what data would \
answer it. Do not guess.
- Be brief. Two or three short paragraphs at most, or a compact list when comparing. No \
preamble, no restating the question. British English.`;

/* ------------------------------------------------------------------ tools */

export const TOOLS = [
  {
    type: "function",
    function: {
      name: "network_summary",
      description:
        "Portfolio-level overview: label counts, score distribution, the model's weights and " +
        "thresholds, and the data-provenance registry. Call this first for any question about " +
        "the network as a whole, or about how the model works.",
      parameters: { type: "object", properties: {}, additionalProperties: false },
    },
  },
  {
    type: "function",
    function: {
      name: "list_branches",
      description:
        "List branches with their scores, labels and key metrics. Use for ranking and filtering " +
        "questions such as 'which branches are most at risk' or 'show me the Abu Dhabi lounges'.",
      parameters: {
        type: "object",
        properties: {
          recommendation: {
            type: "string",
            enum: ["PROTECT", "HOLD", "SHRINK"],
            description: "Filter to one label.",
          },
          emirate: { type: "string", description: "Filter by emirate, e.g. Dubai." },
          sort_by: {
            type: "string",
            enum: [
              "strength",
              "market",
              "rating",
              "review_count",
              "overlap",
              "competitor_count",
              "demand",
            ],
            description: "Field to sort by. Defaults to strength.",
          },
          order: { type: "string", enum: ["asc", "desc"], description: "Defaults to asc." },
          limit: { type: "integer", description: "Max rows, default 10, cap 23." },
        },
        additionalProperties: false,
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_branch",
      description:
        "Full record for one branch, including the signed contribution breakdown of both score " +
        "axes, its competitive set, its overlap with sibling lounges, confidence caveats and its " +
        "pre-generated analyst note. Use this whenever you need to explain WHY a branch got its " +
        "label.",
      parameters: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "Branch id (BD07), area (Palm Jumeirah) or part of the name.",
          },
        },
        required: ["query"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function",
    function: {
      name: "compare_branches",
      description:
        "Side-by-side comparison of two or more branches on every scored signal, with the " +
        "per-signal difference. Use for 'compare X and Y' or 'why is X rated above Y'.",
      parameters: {
        type: "object",
        properties: {
          queries: {
            type: "array",
            items: { type: "string" },
            description: "Two to four branch ids, areas or names.",
          },
        },
        required: ["queries"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function",
    function: {
      name: "find_overlaps",
      description:
        "Pairs of our own lounges whose catchments overlap, with the shared area and the share " +
        "of each branch's catchment given up. Use for cannibalisation and consolidation " +
        "questions.",
      parameters: {
        type: "object",
        properties: {
          min_share: {
            type: "number",
            description: "Only pairs where at least one branch loses this share (0-1).",
          },
          limit: { type: "integer", description: "Max pairs, default 10." },
        },
        additionalProperties: false,
      },
    },
  },
  {
    type: "function",
    function: {
      name: "top_whitespace",
      description:
        "Highest-scoring candidate zones, with their opportunity-score breakdown and distance to " +
        "the nearest existing lounge. Use for 'where should we open' questions.",
      parameters: {
        type: "object",
        properties: {
          metro: { type: "string", description: "Dubai, Abu Dhabi or Sharjah." },
          label: { type: "string", enum: ["GROW", "WATCH", "SKIP"] },
          limit: { type: "integer", description: "Max zones, default 8." },
        },
        additionalProperties: false,
      },
    },
  },
];

/* ------------------------------------------------------- tool implementations */

/** Trim a contribution list to what the model needs to argue from. */
const slimContribs = (axis) =>
  axis.contributions
    .toSorted((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .map((c) => ({
      signal: c.signal,
      label: c.label,
      value: c.raw_display,
      weight: c.weight,
      contribution: c.contribution,
      why: c.explanation,
    }));

const slimBranch = (b) => ({
  branch_id: b.branch_id,
  name: b.name,
  area: b.area,
  emirate: b.emirate,
  recommendation: b.recommendation,
  strength: b.strength.score,
  market: b.market.score,
  rating: b.rating,
  review_count: b.review_count,
  competitor_count: b.competition.competitor_count,
  overlapped_share: b.cannibalisation.overlapped_share,
  demand: b.demand.demand_norm,
});

export function matchBranch(branches, query) {
  const q = String(query).trim().toLowerCase();
  return (
    branches.find((b) => b.branch_id.toLowerCase() === q) ??
    branches.find((b) => b.area.toLowerCase() === q) ??
    branches.find((b) => b.name.toLowerCase().includes(q)) ??
    branches.find((b) => b.area.toLowerCase().includes(q)) ??
    null
  );
}

const SORT_KEYS = {
  strength: (b) => b.strength.score,
  market: (b) => b.market.score,
  rating: (b) => b.rating,
  review_count: (b) => b.review_count,
  overlap: (b) => b.cannibalisation.overlapped_share,
  competitor_count: (b) => b.competition.competitor_count,
  demand: (b) => b.demand.demand_norm,
};

export function runTool(name, args, data) {
  const { branches, zones, overlaps, modelCard } = data;

  switch (name) {
    case "network_summary":
      return {
        counts: modelCard.counts,
        model: {
          strength_weights: modelCard.branch_model.strength_weights,
          market_weights: modelCard.branch_model.market_weights,
          opportunity_weights: modelCard.zone_model.opportunity_weights,
          thresholds: {
            ...modelCard.branch_model.thresholds,
            ...modelCard.zone_model.thresholds,
          },
        },
        geography: modelCard.geography,
        provenance: modelCard.provenance,
        score_range: {
          strength: [
            Math.min(...branches.map((b) => b.strength.score)),
            Math.max(...branches.map((b) => b.strength.score)),
          ],
          market: [
            Math.min(...branches.map((b) => b.market.score)),
            Math.max(...branches.map((b) => b.market.score)),
          ],
        },
      };

    case "list_branches": {
      let rows = branches;
      if (args.recommendation) rows = rows.filter((b) => b.recommendation === args.recommendation);
      if (args.emirate) {
        const e = args.emirate.toLowerCase();
        rows = rows.filter((b) => b.emirate.toLowerCase().includes(e));
      }
      const key = SORT_KEYS[args.sort_by] ?? SORT_KEYS.strength;
      const dir = args.order === "desc" ? -1 : 1;
      rows = rows.toSorted((a, b) => (key(a) - key(b)) * dir);
      const limit = Math.min(args.limit ?? 10, 23);
      return { total_matching: rows.length, branches: rows.slice(0, limit).map(slimBranch) };
    }

    case "get_branch": {
      const b = matchBranch(branches, args.query);
      if (!b) {
        return {
          error: `No branch matches "${args.query}".`,
          available: branches.map((x) => `${x.branch_id} ${x.area}`),
        };
      }
      return {
        ...slimBranch(b),
        address: b.address,
        decision_rule: b.decision_rule,
        catchment_radius_m: b.catchment_radius_m,
        urban_context: b.urban_context,
        strength_breakdown: slimContribs(b.strength),
        market_breakdown: slimContribs(b.market),
        competition: {
          competitor_count: b.competition.competitor_count,
          competitors_per_km2: b.competition.competitors_per_km2,
          competitor_mean_rating: b.competition.competitor_mean_rating,
          our_position_stars: b.competition.competitive_position_stars,
          nearest_rivals: b.competition.top_competitors.slice(0, 5),
        },
        self_overlap: {
          overlapped_share: b.cannibalisation.overlapped_share,
          siblings: b.cannibalisation.siblings,
        },
        confidence: b.confidence,
        analyst_note: b.analyst_note?.text ?? null,
      };
    }

    case "compare_branches": {
      const picked = (args.queries ?? [])
        .slice(0, 4)
        .map((q) => ({ q, b: matchBranch(branches, q) }));
      const missing = picked.filter((p) => !p.b).map((p) => p.q);
      const found = picked.filter((p) => p.b).map((p) => p.b);
      if (found.length < 2) {
        return { error: "Need at least two resolvable branches.", unresolved: missing };
      }
      const signals = [
        ...found[0].strength.contributions.map((c) => c.signal),
        ...found[0].market.contributions.map((c) => c.signal),
      ];
      const byBranch = found.map((b) => {
        const all = [...b.strength.contributions, ...b.market.contributions];
        return {
          branch_id: b.branch_id,
          area: b.area,
          recommendation: b.recommendation,
          strength: b.strength.score,
          market: b.market.score,
          contributions: Object.fromEntries(
            all.map((c) => [c.signal, { value: c.raw_display, contribution: c.contribution }]),
          ),
        };
      });
      return {
        unresolved: missing,
        branches: byBranch,
        // Pre-compute the gaps so the model reports differences rather than
        // doing arithmetic it can get wrong.
        biggest_differences: signals
          .map((s) => {
            const vals = byBranch.map((x) => x.contributions[s]?.contribution ?? 0);
            return { signal: s, spread: Math.max(...vals) - Math.min(...vals) };
          })
          .toSorted((a, b) => b.spread - a.spread)
          .slice(0, 4),
      };
    }

    case "find_overlaps": {
      const min = args.min_share ?? 0;
      const rows = overlaps.features
        .map((f) => f.properties)
        .filter((p) => Math.max(p.share_of_a, p.share_of_b) >= min)
        .toSorted(
          (a, b) => Math.max(b.share_of_a, b.share_of_b) - Math.max(a.share_of_a, a.share_of_b),
        )
        .slice(0, args.limit ?? 10);
      return {
        total_overlapping_pairs: overlaps.features.length,
        pairs: rows.map((p) => ({
          branch_a: `${p.branch_a} ${p.branch_a_name}`,
          branch_b: `${p.branch_b} ${p.branch_b_name}`,
          distance_km: +(p.centroid_distance_m / 1000).toFixed(1),
          shared_area_km2: p.overlap_area_km2,
          share_lost_by_a: p.share_of_a,
          share_lost_by_b: p.share_of_b,
        })),
      };
    }

    case "top_whitespace": {
      let rows = zones;
      if (args.metro) {
        const m = args.metro.toLowerCase();
        rows = rows.filter((z) => z.metro.toLowerCase().includes(m));
      }
      rows = rows.filter((z) => z.recommendation === (args.label ?? z.recommendation));
      if (!args.label) rows = rows.filter((z) => z.recommendation !== "SKIP");
      rows = rows
        .toSorted((a, b) => b.opportunity.score - a.opportunity.score)
        .slice(0, args.limit ?? 8);
      return {
        total_matching: rows.length,
        zones: rows.map((z) => ({
          zone_id: z.zone_id,
          metro: z.metro,
          recommendation: z.recommendation,
          opportunity: z.opportunity.score,
          decision_rule: z.decision_rule,
          nearest_branch: z.nearest_branch_id,
          nearest_branch_km: +(z.nearest_branch_distance_m / 1000).toFixed(1),
          already_covered: z.inside_own_catchment,
          breakdown: slimContribs(z.opportunity),
          mapped_features: {
            residential: z.residential_count,
            everyday_retail: z.activity_count,
            premium: z.affluence_count,
          },
          analyst_note: z.analyst_note?.text ?? null,
        })),
      };
    }

    default:
      return { error: `Unknown tool ${name}` };
  }
}

/* ---------------------------------------------------------------- handler */

/** The dataset is served as static assets from this same deployment, so we
 *  read it over the local origin rather than duplicating it into the bundle.
 *  Cloudflare caches these fetches at the edge, so it is one round trip per
 *  cold isolate rather than one per request. */
async function loadData(requestUrl) {
  const base = new URL(requestUrl).origin;
  const get = async (file) => {
    const res = await fetch(`${base}/data/${file}`, {
      cf: { cacheTtl: 3600, cacheEverything: true },
    });
    if (!res.ok) throw new Error(`could not load ${file} (${res.status})`);
    return res.json();
  };
  const [branches, modelCard, overlaps, whitespace] = await Promise.all([
    get("branches.json"),
    get("model_card.json"),
    get("overlaps.geojson"),
    get("whitespace.geojson"),
  ]);
  return {
    branches,
    modelCard,
    overlaps,
    zones: whitespace.features.map((f) => f.properties),
  };
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

export async function onRequestPost({ request, env }) {
  if (!env.OPENAI_API_KEY) {
    return json(
      {
        error:
          "OPENAI_API_KEY is not configured on this deployment. The map, the scores, the " +
          "recommendations and the pre-generated analyst notes do not need it.",
      },
      501,
    );
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Body must be JSON." }, 400);
  }

  const history = Array.isArray(body?.messages) ? body.messages.slice(-12) : [];
  if (history.length === 0) return json({ error: "No messages supplied." }, 400);

  let data;
  try {
    data = await loadData(request.url);
  } catch (err) {
    return json({ error: `Could not load portfolio data: ${err}` }, 500);
  }

  const messages = [{ role: "system", content: SYSTEM }];
  if (body.context?.selected_branch_id) {
    messages.push({
      role: "system",
      content:
        `The user is currently looking at branch ${body.context.selected_branch_id} on the map. ` +
        `If they ask about "this branch" or "it", they mean that one.`,
    });
  } else if (body.context?.selected_zone_id) {
    messages.push({
      role: "system",
      content:
        `The user is currently looking at candidate zone ${body.context.selected_zone_id}. ` +
        `If they ask about "this zone" or "here", they mean that one.`,
    });
  }
  messages.push(
    ...history
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: String(m.content ?? "") })),
  );

  const trace = [];

  // The tool-calling loop is sequential by necessity: each round's prompt
  // contains the previous round's tool results, so there is nothing to run in
  // parallel. `no-await-in-loop` is good advice for independent work and wrong
  // for a dependent chain.
  /* oxlint-disable no-await-in-loop */
  for (let round = 0; round < MAX_ROUNDS; round++) {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: env.OPENAI_CHAT_MODEL || MODEL,
        temperature: 0.2,
        messages,
        tools: TOOLS,
        tool_choice: "auto",
      }),
    });

    if (!res.ok) {
      const detail = await res.text();
      return json({ error: `OpenAI returned ${res.status}: ${detail.slice(0, 400)}` }, 502);
    }

    const payload = await res.json();
    const choice = payload.choices?.[0];
    const message = choice?.message;
    if (!message) return json({ error: "Malformed response from OpenAI." }, 502);

    messages.push(message);

    const calls = message.tool_calls ?? [];
    if (calls.length === 0) {
      return json({ answer: message.content ?? "", tools: trace, rounds: round + 1 });
    }

    for (const call of calls) {
      let args = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        args = {};
      }
      let result;
      try {
        result = runTool(call.function.name, args, data);
      } catch (err) {
        result = { error: String(err) };
      }
      const serialised = JSON.stringify(result);
      trace.push({
        name: call.function.name,
        arguments: args,
        // A short, human-readable summary for the UI trace. The model gets the
        // full payload; the reviewer gets enough to see the call was real.
        result_summary:
          serialised.length > 400
            ? `${serialised.slice(0, 400)}… (${serialised.length} bytes)`
            : serialised,
      });
      messages.push({ role: "tool", tool_call_id: call.id, content: serialised });
    }
  }

  /* oxlint-enable no-await-in-loop */

  return json(
    {
      answer:
        "I reached the tool-call limit for this question without settling on an answer. Try " +
        "asking something narrower — a single branch, or one metro's whitespace.",
      tools: trace,
      rounds: MAX_ROUNDS,
    },
    200,
  );
}
