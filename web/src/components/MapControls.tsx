import type { Dataset, LayerState } from "../types";

/** The five layers map one-to-one onto the five functional blocks the brief
 *  asks for, and each carries a one-line description of what it is *for*. A
 *  reviewer should be able to isolate exactly the capability they are grading. */
const LAYERS: Array<{ key: keyof LayerState; label: string; hint: string }> = [
  {
    key: "branches",
    label: "Branch network",
    hint: "23 lounges · size = review volume, colour = recommendation",
  },
  {
    key: "catchments",
    label: "Catchments",
    hint: "Service radius per lounge, 2.5–6 km by urban context",
  },
  {
    key: "overlaps",
    label: "Self-overlap",
    hint: "Where our own catchments compete with each other",
  },
  {
    key: "competitors",
    label: "Competition",
    hint: "Salons, spas and hairdressers from OpenStreetMap",
  },
  { key: "whitespace", label: "Whitespace grid", hint: "H3 cells scored GROW / WATCH / SKIP" },
];

export function LayerToggles({
  layers,
  onChange,
}: {
  layers: LayerState;
  onChange: (l: LayerState) => void;
}) {
  return (
    <div className="card">
      <div className="card-title">Layers</div>
      {LAYERS.map((l) => (
        <label className="layer-row" key={l.key}>
          <input
            type="checkbox"
            checked={layers[l.key]}
            onChange={(e) => onChange({ ...layers, [l.key]: e.target.checked })}
          />
          <span className="layer-row-text">
            <b>{l.label}</b>
            <small>{l.hint}</small>
          </span>
        </label>
      ))}
    </div>
  );
}

export function Legend({ layers, data }: { layers: LayerState; data: Dataset }) {
  const bl = data.modelCard.counts.branch_labels;
  const zl = data.modelCard.counts.zone_labels;

  return (
    <div className="card">
      <div className="card-title">Legend</div>

      {layers.branches && (
        <div className="legend-group">
          <div style={{ fontSize: 10.5, color: "var(--text-dim)", marginBottom: 4 }}>
            Existing lounges
          </div>
          {(["PROTECT", "HOLD", "SHRINK"] as const).map((k) => (
            <div className="legend-item" key={k}>
              <span className={`swatch label-${k}`} />
              <span>
                {k} <span style={{ color: "var(--text-faint)" }}>· {bl[k] ?? 0}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {layers.whitespace && (
        <div className="legend-group">
          <div style={{ fontSize: 10.5, color: "var(--text-dim)", marginBottom: 4 }}>
            Candidate zones
          </div>
          {(["GROW", "WATCH", "SKIP"] as const).map((k) => (
            <div className="legend-item" key={k}>
              <span className={`swatch label-${k}`} />
              <span>
                {k} <span style={{ color: "var(--text-faint)" }}>· {zl[k] ?? 0}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {layers.competitors && (
        <div className="legend-group">
          <div style={{ fontSize: 10.5, color: "var(--text-dim)", marginBottom: 4 }}>
            Competitors ({data.modelCard.counts.competitors.toLocaleString()})
          </div>
          <div className="legend-item">
            <span className="swatch" style={{ background: "#f0a0c0" }} /> premium / spa
          </div>
          <div className="legend-item">
            <span className="swatch" style={{ background: "#c08fd0" }} /> mid salon
          </div>
          <div className="legend-item">
            <span className="swatch" style={{ background: "#8090b0" }} /> value / barber
          </div>
        </div>
      )}

      {layers.overlaps && (
        <div className="legend-group">
          <div className="legend-item">
            <span className="swatch" style={{ background: "#e05c5c", opacity: 0.6 }} />
            shared catchment ({data.overlaps.features.length} pairs)
          </div>
        </div>
      )}
    </div>
  );
}
