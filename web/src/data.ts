import type { Dataset } from "./types";

/** Everything the product needs, fetched once from static files that the
 *  Python pipeline wrote. No runtime API, no key, no database — which is what
 *  lets a reviewer clone the repo and see the finished product immediately. */
export async function loadDataset(): Promise<Dataset> {
  const base = import.meta.env.BASE_URL;
  const get = async <T>(file: string): Promise<T> => {
    const res = await fetch(`${base}data/${file}`);
    if (!res.ok) throw new Error(`failed to load ${file}: ${res.status}`);
    return res.json() as Promise<T>;
  };

  const [branches, modelCard, catchments, overlaps, competitors, whitespace] = await Promise.all([
    get<Dataset["branches"]>("branches.json"),
    get<Dataset["modelCard"]>("model_card.json"),
    get<Dataset["catchments"]>("catchments.geojson"),
    get<Dataset["overlaps"]>("overlaps.geojson"),
    get<Dataset["competitors"]>("competitors.geojson"),
    get<Dataset["whitespace"]>("whitespace.geojson"),
  ]);

  return {
    branches,
    modelCard,
    catchments,
    overlaps,
    competitors,
    whitespace,
    zones: whitespace.features.map((f) => f.properties),
  };
}

export const BRANCH_COLOURS: Record<string, string> = {
  PROTECT: "#3fb98a",
  HOLD: "#d9a838",
  SHRINK: "#e05c5c",
};

export const ZONE_COLOURS: Record<string, string> = {
  GROW: "#4a9ede",
  WATCH: "#a07cd4",
  SKIP: "#5b6672",
};

export function fmtKm(metres: number): string {
  return `${(metres / 1000).toFixed(1)} km`;
}

export function fmtPct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function fmtSigned(x: number): string {
  return `${x >= 0 ? "+" : ""}${x.toFixed(3)}`;
}
