import type { Branch, Dataset, Selection, Zone } from "../types";
import { fmtKm, fmtPct } from "../data";
import { ContributionBreakdown } from "./Contributions";

/** Answers the four explainability questions from the brief for whatever is
 *  selected: why this recommendation, what drove it, what the inputs were, and
 *  where to be careful. */

function Prov({ tier }: { tier: "real" | "derived" | "synthetic" }) {
  const title = {
    real: "Real, sourced from a public dataset",
    derived: "Computed by the pipeline from real inputs",
    synthetic: "Simulated — the chain does not publish this",
  }[tier];
  return (
    <span className={`prov prov-${tier}`} title={title}>
      {tier}
    </span>
  );
}

function Note({ note }: { note: Branch["analyst_note"] }) {
  if (!note) {
    return (
      <div className="section">
        <div className="section-head">
          <h3>Analyst note</h3>
        </div>
        <p className="hint">
          No pre-generated note for this record. Notes are produced offline by{" "}
          <code>pipeline/ai/notes.py</code> and committed, so they appear without an API key —
          run <code>--notes</code> to generate the missing ones.
        </p>
      </div>
    );
  }
  return (
    <div className="section">
      <div className="section-head">
        <h3>Analyst note</h3>
      </div>
      <div className="note">
        <div className="note-head">
          <span>AI · {note.model} · grounded in the breakdown above</span>
          {note.stale && <span className="note-stale">stale</span>}
        </div>
        {note.text}
      </div>
    </div>
  );
}

function Confidence({ confidence }: { confidence: Branch["confidence"] }) {
  return (
    <div className="section">
      <div className="section-head">
        <h3>Where to be careful</h3>
        <span className="score">{confidence.level}</span>
      </div>
      {confidence.caveats.length === 0 ? (
        <p className="hint">
          No specific caveats: enough reviews to trust the rating, enough mapped competitors to
          trust the local comparison, and the location resolved precisely. The portfolio-wide
          caveats in “How this works” still apply.
        </p>
      ) : (
        <ul className="caveats">
          {confidence.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BranchDetail({
  branch,
  data,
  onSelect,
}: {
  branch: Branch;
  data: Dataset;
  onSelect: (s: Selection) => void;
}) {
  const c = branch.competition;
  return (
    <>
      <div className="detail-head">
        <h2>{branch.name}</h2>
        <div className="sub">
          {branch.area} · {branch.emirate}
        </div>
        <div className="pill-row">
          <span className={`label-pill label-${branch.recommendation}`}>
            {branch.recommendation}
          </span>
          <span style={{ color: "var(--text-faint)", fontSize: 11 }}>
            strength {branch.strength.score.toFixed(2)} · market {branch.market.score.toFixed(2)}
          </span>
        </div>
        <div className="rule">{branch.decision_rule}</div>
      </div>

      <Note note={branch.analyst_note} />

      <ContributionBreakdown
        axis={branch.strength}
        title="Why — branch strength"
        hint="How well this lounge performs as a business, relative to its own local market. Click a row for the reasoning behind the signal."
      />

      <ContributionBreakdown
        axis={branch.market}
        title="Why — market & defensibility"
        hint="Whether the ground is worth holding: demand in the catchment, room to grow against rivals, less what we already cover ourselves."
      />

      <div className="section">
        <div className="section-head">
          <h3>Inputs</h3>
        </div>
        <dl className="metric-grid">
          <div className="metric">
            <dt>
              Rating <Prov tier="real" />
            </dt>
            <dd>
              {branch.rating.toFixed(1)}★
              <small>{branch.review_count.toLocaleString()} reviews</small>
            </dd>
          </div>
          <div className="metric">
            <dt>
              Momentum <Prov tier="synthetic" />
            </dt>
            <dd>{((branch.momentum - 0.5) * 200).toFixed(0)}%</dd>
          </div>
          <div className="metric">
            <dt>
              Catchment <Prov tier="derived" />
            </dt>
            <dd>
              {(branch.catchment_radius_m / 1000).toFixed(1)} km
              <small>{branch.urban_context.replace("_", " ")}</small>
            </dd>
          </div>
          <div className="metric">
            <dt>
              Chair use <Prov tier="synthetic" />
            </dt>
            <dd>{fmtPct(branch.chair_utilisation)}</dd>
          </div>
          <div className="metric">
            <dt>
              Rivals in catchment <Prov tier="real" />
            </dt>
            <dd>
              {c.competitor_count}
              <small>{c.competitors_per_km2.toFixed(2)}/km²</small>
            </dd>
          </div>
          <div className="metric">
            <dt>
              vs local mean <Prov tier="synthetic" />
            </dt>
            <dd>
              {c.competitive_position_stars >= 0 ? "+" : ""}
              {c.competitive_position_stars.toFixed(2)}★
              <small>rivals {c.competitor_mean_rating.toFixed(2)}★</small>
            </dd>
          </div>
        </dl>
      </div>

      {branch.cannibalisation.sibling_count > 0 && (
        <div className="section">
          <div className="section-head">
            <h3>Own-network overlap</h3>
            <span className="score">{fmtPct(branch.cannibalisation.overlapped_share)}</span>
          </div>
          <p className="hint">
            Share of this catchment also covered by our own lounges, measured as the union of the
            overlaps rather than their sum — three siblings covering the same corner are counted
            once.
          </p>
          <table className="rank-table">
            <tbody>
              {branch.cannibalisation.siblings.map((s) => (
                <tr key={s.branch_id} onClick={() => onSelect({ kind: "branch", id: s.branch_id })}>
                  <td>{data.branches.find((b) => b.branch_id === s.branch_id)?.area ?? s.name}</td>
                  <td className="num">{fmtKm(s.distance_m)}</td>
                  <td className="num">{fmtPct(s.share_of_my_catchment)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {c.top_competitors.length > 0 && (
        <div className="section">
          <div className="section-head">
            <h3>Nearest rivals</h3>
            <span className="score">{c.top_competitors.length} of {c.competitor_count}</span>
          </div>
          <table className="rank-table">
            <thead>
              <tr>
                <th>Venue</th>
                <th>Tier</th>
                <th className="num">Dist</th>
              </tr>
            </thead>
            <tbody>
              {c.top_competitors.map((x) => (
                <tr key={x.competitor_id} style={{ cursor: "default" }}>
                  <td>{x.name}</td>
                  <td style={{ color: "var(--text-faint)" }}>{x.tier}</td>
                  <td className="num">{fmtKm(x.distance_m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Confidence confidence={branch.confidence} />
    </>
  );
}

function ZoneDetail({
  zone,
  data,
  onSelect,
}: {
  zone: Zone;
  data: Dataset;
  onSelect: (s: Selection) => void;
}) {
  const nearest = data.branches.find((b) => b.branch_id === zone.nearest_branch_id);
  return (
    <>
      <div className="detail-head">
        <h2>Candidate zone · {zone.metro}</h2>
        <div className="sub" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
          {zone.zone_id} · {zone.area_km2.toFixed(1)} km² hex
        </div>
        <div className="pill-row">
          <span className={`label-pill label-${zone.recommendation}`}>{zone.recommendation}</span>
          <span style={{ color: "var(--text-faint)", fontSize: 11 }}>
            opportunity {zone.opportunity.score.toFixed(2)}
          </span>
        </div>
        <div className="rule">{zone.decision_rule}</div>
      </div>

      <Note note={zone.analyst_note} />

      <ContributionBreakdown
        axis={zone.opportunity}
        title="Why — opportunity score"
        hint="Demand in the cell, plus how far it sits beyond our existing coverage, less the competition already trading there."
      />

      <div className="section">
        <div className="section-head">
          <h3>Inputs</h3>
        </div>
        <dl className="metric-grid">
          <div className="metric">
            <dt>
              Residential <Prov tier="real" />
            </dt>
            <dd>{zone.residential_count}</dd>
          </div>
          <div className="metric">
            <dt>
              Everyday retail <Prov tier="real" />
            </dt>
            <dd>{zone.activity_count}</dd>
          </div>
          <div className="metric">
            <dt>
              Premium venues <Prov tier="real" />
            </dt>
            <dd>{zone.affluence_count}</dd>
          </div>
          <div className="metric">
            <dt>
              Saturation <Prov tier="derived" />
            </dt>
            <dd>{fmtPct(zone.saturation_norm)}</dd>
          </div>
        </dl>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Nearest lounge</h3>
        </div>
        {nearest ? (
          <table className="rank-table">
            <tbody>
              <tr onClick={() => onSelect({ kind: "branch", id: nearest.branch_id })}>
                <td>{nearest.name}</td>
                <td className="num">{fmtKm(zone.nearest_branch_distance_m)}</td>
                <td className="num">
                  <span className={`label-pill label-${nearest.recommendation}`}>
                    {nearest.recommendation}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="hint">No branch resolved.</p>
        )}
        <p className="hint" style={{ marginTop: 9 }}>
          {zone.inside_own_catchment
            ? "This cell already sits inside that lounge's catchment, so opening here would mostly move revenue rather than add it. The score is damped for that reason."
            : "This cell sits beyond that lounge's catchment, so demand here is genuinely unserved by our network."}
        </p>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Where to be careful</h3>
        </div>
        <ul className="caveats">
          <li>
            Demand is a built-form proxy from OpenStreetMap — residential, retail and premium
            venue density — not census population or income. It under-reads brand-new districts
            that OSM has not mapped yet.
          </li>
          {zone.flags.includes("no_osm_features") && (
            <li>
              No mapped features at all in this cell. Treat the demand figure as unknown rather
              than low.
            </li>
          )}
          {zone.flags.includes("non_residential_zone") && (
            <li>
              Retail and services but no mapped housing: likely a commercial or industrial cell,
              where daytime footfall matters more than the resident pool this model reads.
            </li>
          )}
          <li>
            A hex is a site <em>search area</em>, roughly a neighbourhood, not a site. It says
            where to look, not where to sign.
          </li>
        </ul>
      </div>
    </>
  );
}

function OverlapDetail({
  pairId,
  data,
  onSelect,
}: {
  pairId: string;
  data: Dataset;
  onSelect: (s: Selection) => void;
}) {
  const f = data.overlaps.features.find((x) => x.properties.pair_id === pairId);
  if (!f) return <p className="empty">Overlap not found.</p>;
  const p = f.properties;
  const a = data.branches.find((b) => b.branch_id === p.branch_a);
  const b = data.branches.find((b) => b.branch_id === p.branch_b);

  return (
    <>
      <div className="detail-head">
        <h2>Self-overlap</h2>
        <div className="sub">
          {p.branch_a_name} ∩ {p.branch_b_name}
        </div>
        <div className="rule">
          {p.overlap_area_km2} km² shared · {fmtKm(p.centroid_distance_m)} apart
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Who loses more</h3>
        </div>
        <p className="hint">
          Overlap is asymmetric. The branch giving up the larger share of its own catchment is the
          one under pressure — that asymmetry is what turns "these two are close" into a decision
          about which one to consolidate.
        </p>
        <table className="rank-table">
          <thead>
            <tr>
              <th>Branch</th>
              <th className="num">Share lost</th>
              <th className="num">Label</th>
            </tr>
          </thead>
          <tbody>
            {[
              { b: a, share: p.share_of_a },
              { b: b, share: p.share_of_b },
            ]
              .filter((r) => r.b)
              .sort((x, y) => y.share - x.share)
              .map((r) => (
                <tr
                  key={r.b!.branch_id}
                  onClick={() => onSelect({ kind: "branch", id: r.b!.branch_id })}
                >
                  <td>{r.b!.area}</td>
                  <td className="num">{fmtPct(r.share)}</td>
                  <td className="num">
                    <span className={`label-pill label-${r.b!.recommendation}`}>
                      {r.b!.recommendation}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function DetailPanel({
  selection,
  data,
  onSelect,
}: {
  selection: Selection;
  data: Dataset;
  onSelect: (s: Selection) => void;
}) {
  if (!selection) {
    return (
      <p className="empty">
        Click a lounge, a whitespace hex or an overlap wedge on the map.
        <br />
        <br />
        Every recommendation opens with the signed contribution of each signal that produced it —
        the numbers add up to the score exactly.
      </p>
    );
  }

  if (selection.kind === "branch") {
    const branch = data.branches.find((b) => b.branch_id === selection.id);
    return branch ? (
      <BranchDetail branch={branch} data={data} onSelect={onSelect} />
    ) : (
      <p className="empty">Branch not found.</p>
    );
  }

  if (selection.kind === "zone") {
    const zone = data.zones.find((z) => z.zone_id === selection.id);
    return zone ? (
      <ZoneDetail zone={zone} data={data} onSelect={onSelect} />
    ) : (
      <p className="empty">Zone not found.</p>
    );
  }

  return <OverlapDetail pairId={selection.id} data={data} onSelect={onSelect} />;
}
