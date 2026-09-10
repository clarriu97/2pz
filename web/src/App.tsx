import { useEffect, useMemo, useState } from "react";
import type { Dataset, LayerState, Selection } from "./types";
import { loadDataset } from "./data";
import { MapView } from "./components/MapView";
import { LayerToggles, Legend } from "./components/MapControls";
import { DetailPanel } from "./components/DetailPanel";
import { Ranking, TopZones } from "./components/Ranking";
import { ChatPanel } from "./components/ChatPanel";
import { HowItWorks } from "./components/HowItWorks";

type Tab = "detail" | "compare" | "growth" | "chat" | "about";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "detail", label: "Why" },
  { key: "compare", label: "Compare" },
  { key: "growth", label: "Growth" },
  { key: "chat", label: "Analyst" },
  { key: "about", label: "How" },
];

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [tab, setTab] = useState<Tab>("detail");
  const [layers, setLayers] = useState<LayerState>({
    branches: true,
    catchments: true,
    overlaps: true,
    competitors: false, // thousands of points: opt in, so the first view reads
    whitespace: false, // the network, not a haze
  });

  useEffect(() => {
    loadDataset().then(setData).catch((e) => setError(String(e)));
  }, []);

  /** Selecting from a list should show the reasoning, not leave the reader on
   *  the list they just clicked out of. */
  function select(s: Selection) {
    setSelection(s);
    if (s && (tab === "compare" || tab === "growth")) setTab("detail");
    // Reveal the layer the selection lives on, otherwise clicking a zone in
    // the growth shortlist highlights something invisible.
    if (s?.kind === "zone") setLayers((l) => (l.whitespace ? l : { ...l, whitespace: true }));
  }

  const headline = useMemo(() => {
    if (!data) return null;
    const bl = data.modelCard.counts.branch_labels;
    return `${bl.PROTECT ?? 0} protect · ${bl.HOLD ?? 0} hold · ${bl.SHRINK ?? 0} shrink`;
  }, [data]);

  if (error) {
    return (
      <div className="loading">
        <div style={{ maxWidth: 460, padding: 24 }}>
          <p style={{ color: "var(--shrink)" }}>Could not load the dataset.</p>
          <p style={{ fontSize: 12 }}>{error}</p>
          <p style={{ fontSize: 12 }}>
            The app reads static files from <code>web/public/data/</code>. Generate them with{" "}
            <code>uv run python -m pipeline.run</code> from the repository root.
          </p>
        </div>
      </div>
    );
  }

  if (!data) return <div className="loading">Loading network…</div>;

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <strong>Bedashing Network Intelligence</strong>
          <span>
            Retail network right-sizing · {data.modelCard.counts.branches} lounges ·{" "}
            {headline}
          </span>
        </div>
        <div className="header-persona">
          <span>built for</span>
          <span className="persona-chip">Head of Retail Portfolio</span>
        </div>
      </header>

      <div className="app-body">
        <div className="map-wrap">
          <MapView data={data} layers={layers} selection={selection} onSelect={select} />
          <div className="map-overlay">
            <LayerToggles layers={layers} onChange={setLayers} />
            <Legend layers={layers} data={data} />
          </div>
        </div>

        <div className="panel">
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                className="tab"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "chat" ? (
            // The chat manages its own scrolling, so it takes the whole pane
            // rather than sitting inside the shared scroll container.
            <ChatPanel data={data} onSelect={select} selection={selection} />
          ) : (
            <div className="panel-body">
              {tab === "detail" && (
                <DetailPanel selection={selection} data={data} onSelect={select} />
              )}
              {tab === "compare" && (
                <Ranking data={data} selection={selection} onSelect={select} />
              )}
              {tab === "growth" && <TopZones data={data} onSelect={select} />}
              {tab === "about" && <HowItWorks data={data} />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
