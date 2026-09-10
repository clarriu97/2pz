import { useState } from "react";
import type { AxisScore, Contribution } from "../types";
import { fmtSigned } from "../data";

/** The explainability centrepiece.
 *
 *  Every score in this product is a weighted sum, so the list below is not an
 *  approximation of the model's reasoning — it *is* the model. The bars are
 *  centred on zero and scaled against the largest absolute contribution in the
 *  group, so "this signal dragged the score down" is legible without reading a
 *  single number. Each row expands to the sentence explaining the signal,
 *  because the reviewer's question is "why", not "how much". */

function Row({ c, scale }: { c: Contribution; scale: number }) {
  const [open, setOpen] = useState(false);
  const width = scale > 0 ? (Math.abs(c.contribution) / scale) * 50 : 0;

  return (
    <div className="contrib">
      <div
        className="contrib-top"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      >
        <span className="contrib-name">
          <span className="caret">{open ? "▾" : "▸"}</span>
          {c.label}
        </span>
        <span className={`contrib-value ${c.direction}`}>{fmtSigned(c.contribution)}</span>
      </div>

      <div className="contrib-bar">
        <div
          className={`contrib-fill ${c.contribution >= 0 ? "up" : "down"}`}
          style={{ width: `${width}%` }}
        />
      </div>

      <div className="contrib-meta">
        <span>{c.raw_display}</span>
        <span>
          norm {c.normalised.toFixed(2)} × w {c.weight >= 0 ? "+" : ""}
          {c.weight.toFixed(2)}
        </span>
      </div>

      {open && <p className="contrib-why">{c.explanation}</p>}
    </div>
  );
}

interface Props {
  axis: AxisScore;
  title: string;
  /** One line telling the reader what this axis is *for*, in decision terms. */
  hint: string;
  /** Sort by absolute contribution so the biggest driver is always first —
   *  that answers "what inputs most influenced the outcome?" directly. */
  sortByImpact?: boolean;
}

export function ContributionBreakdown({ axis, title, hint, sortByImpact = true }: Props) {
  const rows = sortByImpact
    ? [...axis.contributions].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    : axis.contributions;
  const scale = Math.max(...rows.map((c) => Math.abs(c.contribution)), 0.001);
  const total = rows.reduce((s, c) => s + c.contribution, 0);

  return (
    <div className="section">
      <div className="section-head">
        <h3>{title}</h3>
        <span className="score">{axis.score.toFixed(3)}</span>
      </div>
      <p className="hint">{hint}</p>
      {rows.map((c) => (
        <Row key={c.signal} c={c} scale={scale} />
      ))}
      <div className="contrib-total">
        <span>sum of contributions</span>
        <span>{total.toFixed(3)}</span>
      </div>
    </div>
  );
}
