import { useMemo, useState } from "react";
import type { Branch, BranchLabel, Dataset, Selection } from "../types";
import { BRANCH_COLOURS, fmtPct } from "../data";

/** "A method for comparing branches", block 4 of the brief.
 *
 *  Sortable on every scored dimension, because which branch is worst depends
 *  entirely on the question being asked: the weakest performer, the most
 *  cannibalised and the most exposed to competition are three different
 *  branches, and a portfolio team needs all three views. */

type Col = {
  key: string;
  label: string;
  num?: boolean;
  get: (b: Branch) => number | string;
  render?: (b: Branch) => React.ReactNode;
};

const COLUMNS: Col[] = [
  {
    key: "area",
    label: "Lounge",
    get: (b) => b.area,
    render: (b) => (
      <>
        <span className="dot" style={{ background: BRANCH_COLOURS[b.recommendation] }} />
        {b.area}
      </>
    ),
  },
  { key: "strength", label: "Strength", num: true, get: (b) => b.strength.score,
    render: (b) => b.strength.score.toFixed(2) },
  { key: "market", label: "Market", num: true, get: (b) => b.market.score,
    render: (b) => b.market.score.toFixed(2) },
  { key: "rating", label: "Rating", num: true, get: (b) => b.rating,
    render: (b) => `${b.rating.toFixed(1)}★` },
  { key: "reviews", label: "Reviews", num: true, get: (b) => b.review_count,
    render: (b) => b.review_count.toLocaleString() },
  { key: "rivals", label: "Rivals", num: true, get: (b) => b.competition.competitor_count,
    render: (b) => String(b.competition.competitor_count) },
  { key: "overlap", label: "Overlap", num: true, get: (b) => b.cannibalisation.overlapped_share,
    render: (b) => fmtPct(b.cannibalisation.overlapped_share) },
];

const FILTERS: Array<BranchLabel | "ALL"> = ["ALL", "PROTECT", "HOLD", "SHRINK"];

export function Ranking({
  data,
  selection,
  onSelect,
}: {
  data: Dataset;
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const [sort, setSort] = useState({ key: "strength", asc: true });
  const [filter, setFilter] = useState<BranchLabel | "ALL">("ALL");

  const rows = useMemo(() => {
    const col = COLUMNS.find((c) => c.key === sort.key) ?? COLUMNS[1];
    const list = data.branches.filter((b) => filter === "ALL" || b.recommendation === filter);
    return [...list].sort((a, b) => {
      const va = col.get(a);
      const vb = col.get(b);
      const cmp = typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb));
      return sort.asc ? cmp : -cmp;
    });
  }, [data.branches, sort, filter]);

  return (
    <>
      <p className="hint">
        Sorted ascending by default, so the branches that need a decision are at the top. Every
        column is a scored input — click a header to re-rank, click a row to open its full
        breakdown.
      </p>

      <div className="suggestions" style={{ marginBottom: 12 }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            className="suggestion"
            style={
              filter === f
                ? { borderColor: "var(--accent-dim)", color: "var(--text)" }
                : undefined
            }
            onClick={() => setFilter(f)}
          >
            {f === "ALL" ? `All ${data.branches.length}` : `${f} ${data.modelCard.counts.branch_labels[f] ?? 0}`}
          </button>
        ))}
      </div>

      <table className="rank-table">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                className={c.num ? "num" : undefined}
                onClick={() =>
                  setSort((s) => ({ key: c.key, asc: s.key === c.key ? !s.asc : true }))
                }
                title={`Sort by ${c.label}`}
              >
                {c.label}
                {sort.key === c.key ? (sort.asc ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr
              key={b.branch_id}
              aria-selected={selection?.kind === "branch" && selection.id === b.branch_id}
              onClick={() => onSelect({ kind: "branch", id: b.branch_id })}
            >
              {COLUMNS.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {c.render ? c.render(b) : String(c.get(b))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/** The growth counterpart: top whitespace cells, since scanning 1,000 hexes on
 *  a map is not how anyone builds a shortlist. */
export function TopZones({
  data,
  onSelect,
}: {
  data: Dataset;
  onSelect: (s: Selection) => void;
}) {
  const rows = useMemo(
    () =>
      [...data.zones]
        .filter((z) => z.recommendation !== "SKIP")
        .sort((a, b) => b.opportunity.score - a.opportunity.score)
        .slice(0, 30),
    [data.zones],
  );

  return (
    <div className="section">
      <div className="section-head">
        <h3>Growth shortlist</h3>
        <span className="score">{rows.length}</span>
      </div>
      <p className="hint">
        The highest-scoring cells that are not foregone SKIPs, across the three gridded metros.
      </p>
      <table className="rank-table">
        <thead>
          <tr>
            <th>Metro</th>
            <th className="num">Score</th>
            <th className="num">Gap</th>
            <th className="num">Label</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((z) => (
            <tr key={z.zone_id} onClick={() => onSelect({ kind: "zone", id: z.zone_id })}>
              <td>{z.metro}</td>
              <td className="num">{z.opportunity.score.toFixed(2)}</td>
              <td className="num">{(z.nearest_branch_distance_m / 1000).toFixed(1)} km</td>
              <td className="num">
                <span className={`label-pill label-${z.recommendation}`}>{z.recommendation}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
