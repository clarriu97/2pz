import type { Dataset } from "../types";

/** Requirement A (business framing) and half of E (where to trust it), placed
 *  inside the product rather than only in the README — a reviewer with fifteen
 *  minutes reads the thing that is on screen. */

function Weights({ title, weights }: { title: string; weights: Record<string, number> }) {
  const scale = Math.max(...Object.values(weights).map(Math.abs));
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 10.5, color: "var(--text-dim)", marginBottom: 5 }}>{title}</div>
      {Object.entries(weights).map(([k, v]) => (
        <div className="contrib" key={k} style={{ padding: "4px 0" }}>
          <div className="contrib-top" style={{ cursor: "default" }}>
            <span className="contrib-name">{k}</span>
            <span className={`contrib-value ${v >= 0 ? "up" : "down"}`}>
              {v >= 0 ? "+" : ""}
              {v.toFixed(2)}
            </span>
          </div>
          <div className="contrib-bar">
            <div
              className={`contrib-fill ${v >= 0 ? "up" : "down"}`}
              style={{ width: `${(Math.abs(v) / scale) * 50}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function HowItWorks({ data }: { data: Dataset }) {
  const mc = data.modelCard;
  const provByTier = { real: [] as string[], derived: [] as string[], synthetic: [] as string[] };
  for (const [field, meta] of Object.entries(mc.provenance)) {
    provByTier[meta.tier].push(field);
  }

  return (
    <>
      <div className="section">
        <div className="section-head">
          <h3>Who this is for</h3>
        </div>
        <p className="hint">
          The <strong>Head of Retail Portfolio</strong> at Bedashing — the person who allocates
          capital across 23 physical lounges. Not "leadership" in general: this is the one role
          that signs a lease, funds a refit, or lets a site go.
        </p>
        <dl className="kv" style={{ marginTop: 8 }}>
          <dt>Decides</dt>
          <dd>PROTECT · HOLD · SHRINK per lounge</dd>
          <dt>Decides</dt>
          <dd>GROW · WATCH · SKIP per candidate zone</dd>
          <dt>Also owns</dt>
          <dd>reducing overlap between our own lounges</dd>
        </dl>
        <p className="hint" style={{ marginTop: 9 }}>
          The three questions this tool has to answer in a portfolio review: which sites are
          earning their footprint, where are we paying rent twice for the same customer, and
          where is there demand we do not reach.
        </p>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>What we would use, and what we actually used</h3>
        </div>
        <p className="hint">
          A real deployment reads revenue per chair, booking density, staff utilisation and lease
          cost from the chain's own systems. None of that is public, so every signal here is a
          public proxy — and each one is labelled in the UI with where it came from, so a number
          is never mistaken for a fact it is not.
        </p>
        <div style={{ marginTop: 10 }}>
          {(["real", "derived", "synthetic"] as const).map((tier) => (
            <div key={tier} style={{ marginBottom: 10 }}>
              <div style={{ marginBottom: 5 }}>
                <span className={`prov prov-${tier}`}>{tier}</span>{" "}
                <span style={{ fontSize: 10.5, color: "var(--text-faint)" }}>
                  {provByTier[tier].length} fields
                </span>
              </div>
              {provByTier[tier].map((f) => (
                <div key={f} className="legend-item" style={{ alignItems: "flex-start" }}>
                  <code style={{ fontSize: 10, color: "var(--text-dim)", flex: "none", width: 130 }}>
                    {f}
                  </code>
                  <span style={{ fontSize: 10.5, color: "var(--text-faint)" }}>
                    {mc.provenance[f].source}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>The model</h3>
        </div>
        <p className="hint">
          A two-axis matrix, not machine learning. Every score is a weighted sum of normalised
          signals, which is why the detail panel can show a breakdown that adds up to the score
          exactly. A committee has to defend a lease decision; "the model said so" is not a
          defence.
        </p>
        <Weights title="Branch strength (X axis)" weights={mc.branch_model.strength_weights} />
        <Weights
          title="Market attractiveness & defensibility (Y axis)"
          weights={mc.branch_model.market_weights}
        />
        <Weights title="Zone opportunity" weights={mc.zone_model.opportunity_weights} />

        <div style={{ fontSize: 10.5, color: "var(--text-dim)", margin: "10px 0 5px" }}>
          Thresholds
        </div>
        <dl className="kv">
          {Object.entries({
            ...mc.branch_model.thresholds,
            ...mc.zone_model.thresholds,
          }).map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <p className="hint" style={{ marginTop: 9 }}>
          All of the above lives in one file, <code>pipeline/config.py</code>. Nothing is
          hard-coded anywhere else, so re-tuning the portfolio's risk appetite is a one-file
          change and this panel updates with it.
        </p>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Geography</h3>
        </div>
        <dl className="kv">
          <dt>catchment</dt>
          <dd>{mc.geography.catchment_method}</dd>
          {Object.entries(mc.geography.catchment_radius_m).map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k.replace("_", " ")}</dt>
              <dd>{(v / 1000).toFixed(1)} km</dd>
            </div>
          ))}
          <dt>grid</dt>
          <dd>H3 res {mc.geography.h3_resolution}</dd>
          <dt>metros gridded</dt>
          <dd>{mc.geography.whitespace_metros.join(", ")}</dd>
        </dl>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Where to be careful</h3>
        </div>
        <ul className="caveats">
          <li>
            <strong>Catchments are radii, not drive times.</strong> A 10-minute isochrone is the
            faithful version; we vary the radius by urban context instead. In the UAE's
            grade-separated grid the gap is smaller than in a European city, but a lounge behind
            a creek or a single bridge is over-credited.
          </li>
          <li>
            <strong>Competitor ratings are simulated.</strong> OpenStreetMap gives us real rival
            locations but no ratings, so "we rate +0.2★ above the local mean" rests on a drawn
            distribution. The direction of that signal is illustrative; the{" "}
            <em>count</em> of rivals is real.
          </li>
          <li>
            <strong>Demand is a built-form proxy.</strong> Residential, retail and premium-venue
            density from OSM, not census population or income. It under-reads newly built
            districts and over-reads tourist strips.
          </li>
          <li>
            <strong>Momentum and chair utilisation are simulated</strong> and seeded from the
            branch id, so they are reproducible but not real. They are in the model to show where
            an operational feed would attach, not to drive a decision today.
          </li>
          <li>
            <strong>Trust the geometry, question the weights.</strong> Overlap area, distances and
            competitor counts are computed from real coordinates and are as good as the inputs.
            The weights that turn them into a label are a stated management judgement, which is
            exactly why they sit in one editable file.
          </li>
        </ul>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>This dataset</h3>
        </div>
        <dl className="kv">
          <dt>generated</dt>
          <dd>{new Date(mc.generated_at).toISOString().slice(0, 16).replace("T", " ")}Z</dd>
          <dt>seed</dt>
          <dd>{mc.seed}</dd>
          <dt>branches</dt>
          <dd>{mc.counts.branches}</dd>
          <dt>competitors</dt>
          <dd>{mc.counts.competitors.toLocaleString()}</dd>
          <dt>scored zones</dt>
          <dd>{mc.counts.scored_zones.toLocaleString()}</dd>
        </dl>
        <p className="hint" style={{ marginTop: 9 }}>
          Every synthetic field is a pure function of the seed and the record id, so re-running
          the pipeline reproduces this dataset byte for byte.
        </p>
      </div>
    </>
  );
}
