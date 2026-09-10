/** Mirrors the shapes written by pipeline/run.py. Kept hand-written rather
 *  than generated: it is short, and it doubles as documentation of the data
 *  contract between the Python pipeline and the product. */

export type BranchLabel = "PROTECT" | "HOLD" | "SHRINK";
export type ZoneLabel = "GROW" | "WATCH" | "SKIP";
export type ProvenanceTier = "real" | "derived" | "synthetic";

/** One signal's signed push on a score. The sum of `contribution` over an
 *  axis equals that axis's score exactly — that identity is what the UI
 *  relies on to claim the breakdown is complete rather than illustrative. */
export interface Contribution {
  signal: string;
  label: string;
  raw_value: number | string;
  raw_display: string;
  normalised: number;
  weight: number;
  contribution: number;
  direction: "up" | "down" | "neutral";
  explanation: string;
}

export interface AxisScore {
  axis: string;
  score: number;
  contributions: Contribution[];
}

export interface AnalystNote {
  text: string;
  model: string;
  stale: boolean;
}

export interface Sibling {
  branch_id: string;
  name: string;
  distance_m: number;
  share_of_my_catchment: number;
}

export interface TopCompetitor {
  competitor_id: string;
  name: string;
  tier: string;
  rating: number;
  distance_m: number;
}

export interface Branch {
  branch_id: string;
  name: string;
  area: string;
  emirate: string;
  address: string;
  lat: number;
  lon: number;
  rating: number;
  review_count: number;
  urban_context: string;
  catchment_radius_m: number;
  momentum: number;
  chair_utilisation: number;
  geocode_precision: string;
  flags: string[];
  recommendation: BranchLabel;
  decision_rule: string;
  strength: AxisScore;
  market: AxisScore;
  top_drivers: string[];
  competition: {
    competitor_count: number;
    competitors_per_km2: number;
    saturation_norm: number;
    competitor_mean_rating: number;
    competitive_position_stars: number;
    premium_share: number;
    nearest_competitor_m: number;
    top_competitors: TopCompetitor[];
  };
  cannibalisation: {
    overlapped_share: number;
    sibling_count: number;
    siblings: Sibling[];
  };
  demand: {
    demand_norm: number;
    cells_in_catchment: number;
    residential_features: number;
    activity_features: number;
    affluence_features: number;
  };
  catchment_area_km2: number;
  confidence: { level: "high" | "medium" | "low"; caveats: string[] };
  analyst_note: AnalystNote | null;
}

export interface Zone {
  zone_id: string;
  metro: string;
  lat: number;
  lon: number;
  area_km2: number;
  residential_count: number;
  activity_count: number;
  affluence_count: number;
  demand_norm: number;
  coverage_gap_norm: number;
  saturation_norm: number;
  nearest_branch_id: string;
  nearest_branch_distance_m: number;
  inside_own_catchment: boolean;
  opportunity: AxisScore;
  recommendation: ZoneLabel;
  decision_rule: string;
  flags: string[];
  analyst_note: AnalystNote | null;
}

export interface ModelCard {
  /** Declared in config, not read from the clock — see pipeline/config.py. */
  sources_as_of: string;
  /** Content hash of the raw inputs and the model parameters. */
  dataset_fingerprint: string;
  seed: number;
  counts: {
    branches: number;
    competitors: number;
    scored_zones: number;
    branch_labels: Record<string, number>;
    zone_labels: Record<string, number>;
  };
  geography: {
    catchment_radius_m: Record<string, number>;
    catchment_method: string;
    h3_resolution: number;
    competitor_search_radius_m: number;
    whitespace_metros: string[];
  };
  branch_model: {
    strength_weights: Record<string, number>;
    market_weights: Record<string, number>;
    thresholds: Record<string, number>;
  };
  zone_model: {
    opportunity_weights: Record<string, number>;
    demand_components: Record<string, number>;
    thresholds: Record<string, number>;
  };
  normalisation: Record<string, number | number[]>;
  provenance: Record<string, { tier: ProvenanceTier; source: string }>;
}

export type FeatureCollection<P> = {
  type: "FeatureCollection";
  features: Array<{ type: "Feature"; geometry: unknown; properties: P }>;
};

export interface Dataset {
  branches: Branch[];
  zones: Zone[];
  modelCard: ModelCard;
  catchments: FeatureCollection<Record<string, unknown>>;
  overlaps: FeatureCollection<{
    pair_id: string;
    branch_a: string;
    branch_a_name: string;
    branch_b: string;
    branch_b_name: string;
    centroid_distance_m: number;
    overlap_area_km2: number;
    share_of_a: number;
    share_of_b: number;
  }>;
  competitors: FeatureCollection<{
    competitor_id: string;
    name: string;
    category: string;
    tier: string;
    rating: number;
    nearest_branch_id: string;
  }>;
  whitespace: FeatureCollection<Zone>;
}

/** Which map layers are visible. One per functional block in the brief, so a
 *  reviewer can isolate exactly the thing they are being asked to judge. */
export interface LayerState {
  branches: boolean;
  catchments: boolean;
  overlaps: boolean;
  competitors: boolean;
  whitespace: boolean;
}

export type Selection =
  | { kind: "branch"; id: string }
  | { kind: "zone"; id: string }
  | { kind: "overlap"; id: string }
  | null;
