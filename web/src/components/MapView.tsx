import { useEffect, useRef } from "react";
import maplibregl, { type Map as MlMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Dataset, LayerState, Selection } from "../types";

/** CARTO's dark basemap: a free, key-free vector style deliberately designed
 *  as a low-chroma backdrop for data overlays. Using a hosted style keeps the
 *  repo free of tile infrastructure. */
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const UAE_BOUNDS: [[number, number], [number, number]] = [
  [54.2, 24.1],
  [56.5, 26.0],
];

/* MapLibre data-driven colour ramps, kept next to the layer definitions so the
   map and the CSS label colours are the only two places colour lives. */
const BRANCH_COLOUR = [
  "match",
  ["get", "recommendation"],
  "PROTECT", "#3fb98a",
  "HOLD", "#d9a838",
  "SHRINK", "#e05c5c",
  "#8b949e",
] as never;

const ZONE_COLOUR = [
  "match",
  ["get", "recommendation"],
  "GROW", "#4a9ede",
  "WATCH", "#a07cd4",
  "SKIP", "#5b6672",
  "#5b6672",
] as never;

interface Props {
  data: Dataset;
  layers: LayerState;
  selection: Selection;
  onSelect: (s: Selection) => void;
}

export function MapView({ data, layers, selection, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);
  // Keep the latest onSelect in a ref: the map's click handlers are registered
  // once on load, and we do not want to tear the map down when a parent
  // re-render hands us a new callback identity.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;

    const m = new maplibregl.Map({
      container: container.current,
      style: BASEMAP,
      bounds: UAE_BOUNDS,
      fitBoundsOptions: { padding: 60 },
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    popup.current = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 10,
    });

    m.on("load", () => {
      const branchPoints = {
        type: "FeatureCollection" as const,
        features: data.branches.map((b) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [b.lon, b.lat] },
          properties: {
            branch_id: b.branch_id,
            name: b.name,
            area: b.area,
            recommendation: b.recommendation,
            rating: b.rating,
            review_count: b.review_count,
          },
        })),
      };

      m.addSource("whitespace", { type: "geojson", data: data.whitespace as never });
      m.addSource("catchments", { type: "geojson", data: data.catchments as never });
      m.addSource("overlaps", { type: "geojson", data: data.overlaps as never });
      m.addSource("competitors", { type: "geojson", data: data.competitors as never });
      m.addSource("branches", { type: "geojson", data: branchPoints });

      /* --- whitespace grid (bottom of the stack) ---------------------- */
      // Hue carries the label; opacity carries demand, so the eye lands on
      // the cells that actually have people in them.
      m.addLayer({
        id: "whitespace-fill",
        type: "fill",
        source: "whitespace",
        paint: {
          "fill-color": ZONE_COLOUR,
          "fill-opacity": ["interpolate", ["linear"], ["get", "demand_norm"], 0, 0.06, 1, 0.55],
        },
      });
      m.addLayer({
        id: "whitespace-line",
        type: "line",
        source: "whitespace",
        paint: { "line-color": ZONE_COLOUR, "line-width": 0.4, "line-opacity": 0.5 },
      });
      // A brighter outline on GROW cells only: the decision layer has to be
      // findable without hunting across a grid of near-identical hexes.
      m.addLayer({
        id: "whitespace-grow",
        type: "line",
        source: "whitespace",
        filter: ["==", ["get", "recommendation"], "GROW"],
        paint: { "line-color": "#7bc4ff", "line-width": 1.6 },
      });

      /* --- catchments -------------------------------------------------- */
      m.addLayer({
        id: "catchment-fill",
        type: "fill",
        source: "catchments",
        paint: { "fill-color": BRANCH_COLOUR, "fill-opacity": 0.07 },
      });
      m.addLayer({
        id: "catchment-line",
        type: "line",
        source: "catchments",
        paint: {
          "line-color": BRANCH_COLOUR,
          "line-width": 1.2,
          "line-dasharray": [3, 2],
          "line-opacity": 0.75,
        },
      });

      /* --- self-overlap: the cannibalisation geometry ------------------ */
      m.addLayer({
        id: "overlap-fill",
        type: "fill",
        source: "overlaps",
        paint: { "fill-color": "#e05c5c", "fill-opacity": 0.22 },
      });
      m.addLayer({
        id: "overlap-line",
        type: "line",
        source: "overlaps",
        paint: { "line-color": "#ff8a8a", "line-width": 1 },
      });

      /* --- competitors ------------------------------------------------- */
      m.addLayer({
        id: "competitor-points",
        type: "circle",
        source: "competitors",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 1.6, 14, 4.5],
          "circle-color": [
            "match",
            ["get", "tier"],
            "premium", "#f0a0c0",
            "mid", "#c08fd0",
            "#8090b0",
          ],
          "circle-opacity": 0.75,
          "circle-stroke-width": 0.4,
          "circle-stroke-color": "#0d1117",
        },
      });

      /* --- our branches (top) ------------------------------------------ */
      m.addLayer({
        id: "branch-points",
        type: "circle",
        source: "branches",
        paint: {
          // Radius encodes review volume, our scale proxy, so the map shows
          // relative size and not just position.
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["sqrt", ["get", "review_count"]],
            5, 5,
            38, 15,
          ],
          "circle-color": BRANCH_COLOUR,
          "circle-opacity": 0.9,
          "circle-stroke-width": 1.4,
          "circle-stroke-color": "#0d1117",
        },
      });
      m.addLayer({
        id: "branch-selected",
        type: "circle",
        source: "branches",
        filter: ["==", ["get", "branch_id"], "__none__"],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["sqrt", ["get", "review_count"]],
            5, 9,
            38, 19,
          ],
          "circle-color": "transparent",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
      m.addLayer({
        id: "branch-labels",
        type: "symbol",
        source: "branches",
        minzoom: 9,
        layout: {
          "text-field": ["get", "area"],
          "text-size": 11,
          "text-offset": [0, 1.5],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#e6edf3",
          "text-halo-color": "#0d1117",
          "text-halo-width": 1.4,
        },
      });

      /* --- interaction -------------------------------------------------- */
      const hoverable: Array<[string, (p: Record<string, never>) => string]> = [
        [
          "branch-points",
          (p) =>
            `<strong>${p.name}</strong><br>${p.recommendation} · ${p.rating}★ · ` +
            `${Number(p.review_count).toLocaleString()} reviews`,
        ],
        [
          "whitespace-fill",
          (p) =>
            `<strong>${p.recommendation}</strong> · ${p.metro}<br>` +
            `${(Number(p.nearest_branch_distance_m) / 1000).toFixed(1)} km to nearest lounge`,
        ],
        [
          "overlap-fill",
          (p) =>
            `<strong>Self-overlap</strong><br>${p.branch_a_name} ∩ ${p.branch_b_name}<br>` +
            `${p.overlap_area_km2} km² shared`,
        ],
        ["competitor-points", (p) => `<strong>${p.name}</strong><br>${p.tier} · ${p.category}`],
      ];

      for (const [layer, render] of hoverable) {
        m.on("mousemove", layer, (e) => {
          if (!e.features?.length) return;
          m.getCanvas().style.cursor = "pointer";
          popup.current
            ?.setLngLat(e.lngLat)
            .setHTML(render(e.features[0].properties as Record<string, never>))
            .addTo(m);
        });
        m.on("mouseleave", layer, () => {
          m.getCanvas().style.cursor = "";
          popup.current?.remove();
        });
      }

      m.on("click", "branch-points", (e) => {
        const id = e.features?.[0]?.properties?.branch_id;
        if (id) onSelectRef.current({ kind: "branch", id: String(id) });
      });
      m.on("click", "whitespace-fill", (e) => {
        const id = e.features?.[0]?.properties?.zone_id;
        if (id) onSelectRef.current({ kind: "zone", id: String(id) });
      });
      m.on("click", "overlap-fill", (e) => {
        const id = e.features?.[0]?.properties?.pair_id;
        if (id) onSelectRef.current({ kind: "overlap", id: String(id) });
      });
    });

    return () => {
      m.remove();
      map.current = null;
    };
  }, [data]);

  /* Layer visibility. Driven by props rather than by imperative toggles so the
     checkbox state and the map can never drift apart. */
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const groups: Record<keyof LayerState, string[]> = {
        branches: ["branch-points", "branch-labels", "branch-selected"],
        catchments: ["catchment-fill", "catchment-line"],
        overlaps: ["overlap-fill", "overlap-line"],
        competitors: ["competitor-points"],
        whitespace: ["whitespace-fill", "whitespace-line", "whitespace-grow"],
      };
      for (const [key, ids] of Object.entries(groups)) {
        const visible = layers[key as keyof LayerState] ? "visible" : "none";
        for (const id of ids) {
          if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", visible);
        }
      }
    };
    if (m.isStyleLoaded() && m.getLayer("branch-points")) apply();
    else m.once("idle", apply);
  }, [layers, data]);

  /* Fly to and highlight the current selection. */
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const apply = () => {
      if (m.getLayer("branch-selected")) {
        m.setFilter("branch-selected", [
          "==",
          ["get", "branch_id"],
          selection?.kind === "branch" ? selection.id : "__none__",
        ]);
      }
      if (!selection) return;
      if (selection.kind === "branch") {
        const b = data.branches.find((x) => x.branch_id === selection.id);
        if (b) m.easeTo({ center: [b.lon, b.lat], zoom: Math.max(m.getZoom(), 11), duration: 700 });
      } else if (selection.kind === "zone") {
        const z = data.zones.find((x) => x.zone_id === selection.id);
        if (z) m.easeTo({ center: [z.lon, z.lat], zoom: Math.max(m.getZoom(), 11), duration: 700 });
      } else if (selection.kind === "overlap") {
        const f = data.overlaps.features.find((x) => x.properties.pair_id === selection.id);
        const a = data.branches.find((x) => x.branch_id === f?.properties.branch_a);
        const b = data.branches.find((x) => x.branch_id === f?.properties.branch_b);
        if (a && b) {
          m.fitBounds(
            [
              [Math.min(a.lon, b.lon), Math.min(a.lat, b.lat)],
              [Math.max(a.lon, b.lon), Math.max(a.lat, b.lat)],
            ],
            { padding: 140, duration: 700 },
          );
        }
      }
    };

    if (m.isStyleLoaded() && m.getLayer("branch-selected")) apply();
    else m.once("idle", apply);
  }, [selection, data]);

  return <div className="map" ref={container} />;
}
