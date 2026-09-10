import { afterEach, describe, expect, it, vi } from "vitest";
import { BRANCH_COLOURS, ZONE_COLOURS, fmtKm, fmtPct, fmtSigned, loadDataset } from "./data";
import { dataset } from "./test/fixtures";

describe("formatters", () => {
  it("renders distances in kilometres to one decimal", () => {
    expect(fmtKm(3730)).toBe("3.7 km");
    expect(fmtKm(0)).toBe("0.0 km");
  });

  it("renders shares as percentages", () => {
    expect(fmtPct(0.43)).toBe("43%");
    expect(fmtPct(0.4312, 1)).toBe("43.1%");
  });

  it("always shows the sign on a contribution", () => {
    // The sign is the whole point of a signed contribution: "+0.180" and
    // "-0.180" must never render identically.
    expect(fmtSigned(0.18)).toBe("+0.180");
    expect(fmtSigned(-0.18)).toBe("-0.180");
    expect(fmtSigned(0)).toBe("+0.000");
  });
});

describe("label colours", () => {
  it("covers every branch and zone label", () => {
    expect(Object.keys(BRANCH_COLOURS).toSorted()).toEqual(["HOLD", "PROTECT", "SHRINK"]);
    expect(Object.keys(ZONE_COLOURS).toSorted()).toEqual(["GROW", "SKIP", "WATCH"]);
  });

  it("gives every label a distinct colour", () => {
    const all = [...Object.values(BRANCH_COLOURS), ...Object.values(ZONE_COLOURS)];
    expect(new Set(all).size).toBe(all.length);
  });
});

/** Serves the six static files the app fetches, and records the URLs asked
 *  for so a test can assert every layer was requested. */
function stubFetch(files: Record<string, unknown>, ok = true) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const name = url.split("/").pop()!;
      return { ok, status: ok ? 200 : 404, json: async () => files[name] };
    }),
  );
  return calls;
}

describe("loadDataset", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches every layer the product needs", async () => {
    const d = dataset();
    const calls = stubFetch({
      "branches.json": d.branches,
      "model_card.json": d.modelCard,
      "catchments.geojson": d.catchments,
      "overlaps.geojson": d.overlaps,
      "competitors.geojson": d.competitors,
      "whitespace.geojson": d.whitespace,
    });

    const loaded = await loadDataset();
    expect(calls.map((c) => c.split("/").pop()).toSorted()).toEqual([
      "branches.json",
      "catchments.geojson",
      "competitors.geojson",
      "model_card.json",
      "overlaps.geojson",
      "whitespace.geojson",
    ]);
    expect(loaded.branches).toHaveLength(3);
  });

  it("derives the zone list from the whitespace layer rather than a second file", async () => {
    // One source of truth: the hexes on the map and the rows in the growth
    // shortlist must be the same records, or they can disagree.
    const d = dataset();
    stubFetch({
      "branches.json": d.branches,
      "model_card.json": d.modelCard,
      "catchments.geojson": d.catchments,
      "overlaps.geojson": d.overlaps,
      "competitors.geojson": d.competitors,
      "whitespace.geojson": d.whitespace,
    });

    const loaded = await loadDataset();
    expect(loaded.zones).toHaveLength(d.whitespace.features.length);
    expect(loaded.zones[0].zone_id).toBe(d.whitespace.features[0].properties.zone_id);
  });

  it("names the missing file when a fetch fails", async () => {
    stubFetch({}, false);
    // A silent empty dataset would render as a blank map; the error has to say
    // which file the reviewer needs to generate.
    await expect(loadDataset()).rejects.toThrow(/failed to load .*: 404/);
  });
});
