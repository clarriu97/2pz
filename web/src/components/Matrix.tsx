import { useMemo, useState } from "react";
import type { Branch, Dataset, Selection } from "../types";
import { BRANCH_COLOURS } from "../data";

/** The two-axis matrix, drawn.
 *
 *  The model *is* a two-axis matrix, but until now that was only ever stated —
 *  the detail panel shows one branch at a time and the table sorts on one
 *  column at a time, so the shape of the portfolio was never visible. This is
 *  the one view where "strong branch, weak ground" reads instantly: a lounge
 *  sitting top-left is being flagged despite performing well, which is exactly
 *  the distinction a single ranking would have buried.
 */

const PAD = { top: 18, right: 18, bottom: 42, left: 52 };
const VIEW = { w: 520, h: 400 };

/** Axis bounds that contain both the data and every threshold line.
 *
 *  A fixed 0–1 domain would squeeze all 23 branches into a corner: strength
 *  spans roughly 0.45–0.78 and market 0.26–0.58. Fitting to the data alone
 *  would risk pushing a threshold line off the chart, and the thresholds are
 *  the whole point of the picture.
 */
function domain(values: number[], thresholds: number[]): [number, number] {
  const all = [...values, ...thresholds];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const margin = Math.max((hi - lo) * 0.12, 0.02);
  return [lo - margin, hi + margin];
}

export function Matrix({
  data,
  selection,
  onSelect,
}: {
  data: Dataset;
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const t = data.modelCard.branch_model.thresholds;

  const { xScale, yScale, points } = useMemo(() => {
    const branches = data.branches;
    const [x0, x1] = domain(
      branches.map((b) => b.strength.score),
      [t.strength_low, t.strength_high],
    );
    const [y0, y1] = domain(
      branches.map((b) => b.market.score),
      [t.market_low, t.market_high],
    );

    const plotW = VIEW.w - PAD.left - PAD.right;
    const plotH = VIEW.h - PAD.top - PAD.bottom;
    const toX = (v: number) => PAD.left + ((v - x0) / (x1 - x0)) * plotW;
    // SVG y grows downward, so a high market score has to map to a small y.
    const toY = (v: number) => PAD.top + (1 - (v - y0) / (y1 - y0)) * plotH;

    const maxReviews = Math.max(...branches.map((b) => b.review_count));
    return {
      xScale: toX,
      yScale: toY,
      points: branches.map((b) => ({
        branch: b,
        cx: toX(b.strength.score),
        cy: toY(b.market.score),
        // Area, not radius, tracks review volume — the same scale proxy the
        // map uses, so a branch is the same size in both views.
        r: 4 + 9 * Math.sqrt(b.review_count / maxReviews),
      })),
    };
  }, [data.branches, t]);

  const selectedId = selection?.kind === "branch" ? selection.id : null;
  const active = hovered ?? selectedId;
  const activeBranch = active ? data.branches.find((b) => b.branch_id === active) : undefined;

  return (
    <div className="section">
      <div className="section-head">
        <h3>The decision matrix</h3>
        <span className="score">{data.branches.length} lounges</span>
      </div>
      <p className="hint">
        Every lounge on both axes at once. The lines are the thresholds from <code>config.py</code>;
        circle area is review volume. A lounge high on the left is being flagged <em>despite</em>{" "}
        performing well — that is cannibalisation, not underperformance, and a single ranking would
        have hidden it.
      </p>

      <svg
        className="matrix"
        viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
        role="img"
        aria-label="Branch strength against market attractiveness, with threshold lines"
      >
        {/* Quadrant shading: the PROTECT corner and the SHRINK strip. */}
        <rect
          x={xScale(t.strength_high)}
          y={PAD.top}
          width={VIEW.w - PAD.right - xScale(t.strength_high)}
          height={yScale(t.market_high) - PAD.top}
          className="matrix-zone matrix-zone-protect"
        />
        <rect
          x={PAD.left}
          y={PAD.top}
          width={xScale(t.strength_low) - PAD.left}
          height={VIEW.h - PAD.bottom - PAD.top}
          className="matrix-zone matrix-zone-shrink"
        />

        {/* Threshold lines */}
        <line
          x1={xScale(t.strength_high)}
          x2={xScale(t.strength_high)}
          y1={PAD.top}
          y2={VIEW.h - PAD.bottom}
          className="matrix-threshold"
        />
        <line
          x1={xScale(t.strength_low)}
          x2={xScale(t.strength_low)}
          y1={PAD.top}
          y2={VIEW.h - PAD.bottom}
          className="matrix-threshold"
        />
        <line
          x1={PAD.left}
          x2={VIEW.w - PAD.right}
          y1={yScale(t.market_high)}
          y2={yScale(t.market_high)}
          className="matrix-threshold"
        />
        <line
          x1={PAD.left}
          x2={VIEW.w - PAD.right}
          y1={yScale(t.market_low)}
          y2={yScale(t.market_low)}
          className="matrix-threshold"
        />

        {/* Axes */}
        <line
          x1={PAD.left}
          x2={VIEW.w - PAD.right}
          y1={VIEW.h - PAD.bottom}
          y2={VIEW.h - PAD.bottom}
          className="matrix-axis"
        />
        <line
          x1={PAD.left}
          x2={PAD.left}
          y1={PAD.top}
          y2={VIEW.h - PAD.bottom}
          className="matrix-axis"
        />

        <text x={VIEW.w / 2} y={VIEW.h - 8} className="matrix-axis-label" textAnchor="middle">
          Branch strength →
        </text>
        <text
          x={-VIEW.h / 2}
          y={14}
          className="matrix-axis-label"
          textAnchor="middle"
          transform="rotate(-90)"
        >
          Market &amp; defensibility →
        </text>

        {/* Threshold values, so the reader can tie the lines to config.py */}
        <text
          x={xScale(t.strength_high)}
          y={VIEW.h - PAD.bottom + 14}
          className="matrix-tick"
          textAnchor="middle"
        >
          {t.strength_high}
        </text>
        <text
          x={xScale(t.strength_low)}
          y={VIEW.h - PAD.bottom + 14}
          className="matrix-tick"
          textAnchor="middle"
        >
          {t.strength_low}
        </text>
        <text
          x={PAD.left - 8}
          y={yScale(t.market_high) + 4}
          className="matrix-tick"
          textAnchor="end"
        >
          {t.market_high}
        </text>
        <text
          x={PAD.left - 8}
          y={yScale(t.market_low) + 4}
          className="matrix-tick"
          textAnchor="end"
        >
          {t.market_low}
        </text>

        {/* Branches. Drawn largest-first so a small point is never buried. */}
        {points
          .toSorted((a, b) => b.r - a.r)
          .map(({ branch, cx, cy, r }) => {
            const isActive = active === branch.branch_id;
            return (
              <g key={branch.branch_id}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={BRANCH_COLOURS[branch.recommendation]}
                  className={`matrix-point${isActive ? " is-active" : ""}`}
                  onClick={() => onSelect({ kind: "branch", id: branch.branch_id })}
                  onMouseEnter={() => setHovered(branch.branch_id)}
                  onMouseLeave={() => setHovered(null)}
                  role="button"
                  tabIndex={0}
                  aria-label={`${branch.area}: strength ${branch.strength.score.toFixed(
                    2,
                  )}, market ${branch.market.score.toFixed(2)}, ${branch.recommendation}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect({ kind: "branch", id: branch.branch_id });
                    }
                  }}
                />
                {isActive && (
                  <text x={cx} y={cy - r - 6} className="matrix-point-label" textAnchor="middle">
                    {branch.area}
                  </text>
                )}
              </g>
            );
          })}
      </svg>

      <MatrixReadout branch={activeBranch} thresholds={t} />
    </div>
  );
}

/** One line under the chart, so hovering a point answers "which and why". */
function MatrixReadout({
  branch,
  thresholds,
}: {
  branch: Branch | undefined;
  thresholds: Record<string, number>;
}) {
  if (!branch) {
    return (
      <p className="hint matrix-readout">
        Hover or click a lounge. Top-right is PROTECT (strength ≥ {thresholds.strength_high} and
        market ≥ {thresholds.market_high}); the left strip is SHRINK on weak strength.
      </p>
    );
  }
  return (
    <p className="hint matrix-readout">
      <span className={`label-pill label-${branch.recommendation}`}>{branch.recommendation}</span>{" "}
      <strong>{branch.area}</strong> · strength {branch.strength.score.toFixed(2)} · market{" "}
      {branch.market.score.toFixed(2)} · {branch.review_count.toLocaleString()} reviews ·{" "}
      {(branch.cannibalisation.overlapped_share * 100).toFixed(0)}% overlap
    </p>
  );
}
