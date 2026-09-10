import type { AxisScore, Branch, Contribution, Dataset, ModelCard, Zone } from "../types";

/** A small, hand-built dataset.
 *
 *  Deliberately not a slice of the real committed data: the assertions below
 *  are about ordering, signs and thresholds, and those read far better against
 *  numbers chosen to make the expected answer obvious.
 */

export function contribution(over: Partial<Contribution> = {}): Contribution {
  const value = over.contribution ?? 0.2;
  return {
    signal: "rating_norm",
    label: "Guest rating",
    raw_value: 4.6,
    raw_display: "4.6★",
    normalised: 0.67,
    weight: 0.3,
    contribution: value,
    direction: value > 0 ? "up" : value < 0 ? "down" : "neutral",
    explanation: "A long enough explanation to be worth showing to a reviewer.",
    ...over,
  };
}

export function axis(over: Partial<AxisScore> = {}): AxisScore {
  const contributions = over.contributions ?? [
    contribution({ signal: "rating_norm", label: "Guest rating", contribution: 0.2 }),
    contribution({ signal: "momentum", label: "Recent momentum", contribution: -0.05 }),
    contribution({ signal: "review_volume_norm", label: "Review volume", contribution: 0.18 }),
  ];
  return {
    axis: "strength",
    score: Number(contributions.reduce((s, c) => s + c.contribution, 0).toFixed(4)),
    contributions,
    ...over,
  };
}

export function branch(over: Partial<Branch> = {}): Branch {
  return {
    branch_id: "BD01",
    name: "Bedashing Alpha",
    area: "Mirdif",
    emirate: "Dubai",
    address: "Mirdif, Dubai",
    lat: 25.2218,
    lon: 55.4231,
    rating: 4.6,
    review_count: 568,
    urban_context: "suburban",
    catchment_radius_m: 4000,
    momentum: 0.55,
    chair_utilisation: 0.62,
    geocode_precision: "area",
    flags: [],
    recommendation: "HOLD",
    decision_rule: "strength 0.63 and market 0.48 fall between the PROTECT and SHRINK thresholds",
    strength: axis({ axis: "strength" }),
    market: axis({
      axis: "market",
      contributions: [
        contribution({ signal: "demand_norm", label: "Catchment demand", contribution: 0.27 }),
        contribution({
          signal: "headroom_norm",
          label: "Competitive headroom",
          contribution: 0.14,
        }),
        contribution({
          signal: "cannibalisation_penalty",
          label: "Self-cannibalisation",
          contribution: -0.09,
        }),
      ],
    }),
    top_drivers: ["demand_norm", "rating_norm", "review_volume_norm"],
    competition: {
      competitor_count: 18,
      competitors_per_km2: 0.36,
      saturation_norm: 0.42,
      competitor_mean_rating: 4.41,
      competitive_position_stars: 0.19,
      premium_share: 0.11,
      nearest_competitor_m: 340,
      top_competitors: [
        {
          competitor_id: "n1",
          name: "Rival Beauty",
          tier: "mid",
          rating: 4.4,
          distance_m: 340,
        },
      ],
    },
    cannibalisation: {
      overlapped_share: 0.43,
      sibling_count: 1,
      siblings: [
        {
          branch_id: "BD02",
          name: "Bedashing Beta",
          distance_m: 3730,
          share_of_my_catchment: 0.43,
        },
      ],
    },
    demand: {
      demand_norm: 0.6,
      cells_in_catchment: 5,
      residential_features: 240,
      activity_features: 96,
      affluence_features: 14,
    },
    catchment_area_km2: 50.265,
    confidence: { level: "high", caveats: [] },
    analyst_note: {
      text: "Holds its ground on quality but shares 43% of its catchment with Beta.",
      model: "gpt-4.1-mini",
      stale: false,
    },
    ...over,
  };
}

export function zone(over: Partial<Zone> = {}): Zone {
  return {
    zone_id: "871e1d0ffffffff",
    metro: "Dubai",
    lat: 25.24,
    lon: 55.31,
    area_km2: 5.16,
    residential_count: 62,
    activity_count: 24,
    affluence_count: 7,
    demand_norm: 0.58,
    coverage_gap_norm: 0.71,
    saturation_norm: 0.18,
    nearest_branch_id: "BD01",
    nearest_branch_distance_m: 6800,
    inside_own_catchment: false,
    opportunity: axis({
      axis: "opportunity",
      contributions: [
        contribution({ signal: "demand_norm", label: "Zone demand", contribution: 0.26 }),
        contribution({ signal: "coverage_gap_norm", label: "Coverage gap", contribution: 0.25 }),
        contribution({
          signal: "saturation_norm",
          label: "Competitive saturation",
          contribution: -0.04,
        }),
      ],
    }),
    recommendation: "GROW",
    decision_rule: "opportunity 0.47 ≥ 0.45",
    flags: [],
    analyst_note: null,
    ...over,
  };
}

export function modelCard(over: Partial<ModelCard> = {}): ModelCard {
  return {
    sources_as_of: "2026-09-10",
    dataset_fingerprint: "89ab39341d83260b",
    seed: 20260910,
    counts: {
      branches: 3,
      competitors: 1354,
      scored_zones: 2,
      branch_labels: { PROTECT: 1, HOLD: 1, SHRINK: 1 },
      zone_labels: { GROW: 1, WATCH: 1 },
    },
    geography: {
      catchment_radius_m: { dense_urban: 2500, suburban: 4000, low_density: 6000 },
      catchment_method: "haversine radius by urban context",
      h3_resolution: 7,
      competitor_search_radius_m: 5000,
      whitespace_metros: ["Dubai", "Abu Dhabi", "Sharjah"],
    },
    branch_model: {
      strength_weights: {
        rating_norm: 0.3,
        review_volume_norm: 0.25,
        momentum: 0.2,
        competitive_position: 0.25,
      },
      market_weights: {
        demand_norm: 0.45,
        headroom_norm: 0.35,
        cannibalisation_penalty: -0.2,
      },
      thresholds: { strength_high: 0.58, strength_low: 0.42 },
    },
    zone_model: {
      opportunity_weights: {
        demand_norm: 0.45,
        coverage_gap_norm: 0.35,
        saturation_norm: -0.2,
      },
      demand_components: { residential: 0.4, activity: 0.25, affluence: 0.35 },
      thresholds: { grow: 0.62, watch: 0.45 },
    },
    normalisation: { rating_band: [4.2, 4.95] },
    provenance: {
      "branch.rating": { tier: "real", source: "Public Google Maps rating aggregate" },
      catchment: { tier: "derived", source: "Haversine radius by urban context" },
      "branch.momentum": { tier: "synthetic", source: "Simulated recent-review trend (seeded)" },
    },
    ...over,
  };
}

function polygonFeature(properties: Record<string, unknown>) {
  return {
    type: "Feature" as const,
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [55.3, 25.2],
          [55.31, 25.2],
          [55.31, 25.21],
          [55.3, 25.21],
          [55.3, 25.2],
        ],
      ],
    },
    properties,
  };
}

export function dataset(over: Partial<Dataset> = {}): Dataset {
  const branches: Branch[] = [
    branch({ branch_id: "BD01", area: "Mirdif", recommendation: "HOLD" }),
    branch({
      branch_id: "BD02",
      name: "Bedashing Beta",
      area: "Al Warqa",
      emirate: "Dubai",
      recommendation: "SHRINK",
      rating: 4.5,
      review_count: 150,
      strength: axis({
        axis: "strength",
        contributions: [contribution({ contribution: 0.1 })],
      }),
      cannibalisation: {
        overlapped_share: 0.56,
        sibling_count: 1,
        siblings: [
          {
            branch_id: "BD01",
            name: "Bedashing Alpha",
            distance_m: 3730,
            share_of_my_catchment: 0.56,
          },
        ],
      },
      confidence: { level: "low", caveats: ["Only 150 reviews.", "Only 2 rivals mapped."] },
      analyst_note: { text: "Stale note.", model: "gpt-4.1-mini", stale: true },
    }),
    branch({
      branch_id: "BD03",
      name: "Bedashing Gamma",
      area: "Al Ain",
      emirate: "Abu Dhabi",
      recommendation: "PROTECT",
      rating: 4.8,
      review_count: 829,
      cannibalisation: { overlapped_share: 0, sibling_count: 0, siblings: [] },
      analyst_note: null,
    }),
  ];

  const zones: Zone[] = [
    zone(),
    zone({
      zone_id: "871e1d1ffffffff",
      metro: "Abu Dhabi",
      recommendation: "WATCH",
      inside_own_catchment: true,
      nearest_branch_distance_m: 1200,
      flags: ["non_residential_zone"],
      opportunity: axis({
        axis: "opportunity",
        contributions: [contribution({ signal: "demand_norm", contribution: 0.12 })],
      }),
    }),
  ];

  return {
    branches,
    zones,
    modelCard: modelCard(),
    catchments: {
      type: "FeatureCollection",
      features: branches.map((b) => polygonFeature({ branch_id: b.branch_id, name: b.name })),
    },
    overlaps: {
      type: "FeatureCollection",
      features: [
        polygonFeature({
          pair_id: "BD01~BD02",
          branch_a: "BD01",
          branch_a_name: "Bedashing Alpha",
          branch_b: "BD02",
          branch_b_name: "Bedashing Beta",
          centroid_distance_m: 3730,
          overlap_area_km2: 21.6,
          share_of_a: 0.43,
          share_of_b: 0.56,
        }),
      ] as never,
    },
    competitors: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [55.3, 25.2] },
          properties: {
            competitor_id: "n1",
            name: "Rival Beauty",
            category: "beauty_salon",
            tier: "mid",
            rating: 4.4,
            nearest_branch_id: "BD01",
          },
        },
      ],
    },
    whitespace: {
      type: "FeatureCollection",
      features: zones.map((z) => polygonFeature(z as never)) as never,
    },
    ...over,
  };
}
