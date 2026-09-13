import { useEffect, useRef, useState } from "react";
// Type-only, so this does not make a runtime cycle with App: the tour walks
// the panel's tabs, which means it has to speak in their names.
import type { Tab } from "../App";

/** A five-step first-run tour.
 *
 *  No library and no portal: each step names an element already on the page,
 *  and the overlay is one div with a hole punched in it by an outsized
 *  box-shadow around that element's rectangle. Everything it teaches is
 *  visible behind the dimming, which is the point — the reader is looking at
 *  the real product, not at pictures of it.
 *
 *  Seen-ness lives in localStorage, so this is per-browser and disappears the
 *  moment someone clears site data. That is the right weight for a tutorial:
 *  losing it costs fifteen seconds. */

const SEEN_KEY = "bedashing.tour.v1";

export interface TourStep {
  /** The element to cut out of the overlay. A step whose target is missing
   *  leaves the card centred rather than pointing at empty space. */
  target: string;
  /** Opened as the step appears, so the panel behind the dimming is showing
   *  the thing being described. */
  tab?: Tab;
  title: string;
  body: string;
}

export const STEPS: TourStep[] = [
  {
    target: ".map-overlay",
    title: "The map is the network",
    body: "Every lounge, sized by review volume and coloured by recommendation. Turn layers on and off here — Competition and Whitespace start off so the first view reads as your own network.",
  },
  {
    target: ".panel .tabs",
    tab: "detail",
    title: "Why: the reasoning, never a verdict",
    body: "Click a lounge, a whitespace hex or an overlap wedge, and this tab shows the signed contribution of every signal behind its score. The numbers add up to the score exactly.",
  },
  {
    target: ".panel .tabs",
    tab: "compare",
    title: "Compare and Growth: the two lists",
    body: "Compare ranks all 23 lounges on every scored signal, sortable by any column. Growth is the whitespace shortlist — where there is demand you do not reach yet.",
  },
  {
    target: ".panel .tabs",
    tab: "about",
    title: "How: where not to trust this",
    body: "Who it is for, where each field came from, the model's weights, and the caveats. Worth two minutes before you act on anything here.",
  },
  {
    target: ".analyst-launcher",
    title: "Ask the analyst",
    body: "Questions in plain language, answered by calling tools over this same data — and every answer shows which calls produced it. Whatever you have selected is offered as context.",
  },
];

/** localStorage throws outright in some privacy modes, so every access is
 *  guarded: a tutorial must never be the reason the page fails to load. */
export function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    // Unreadable storage means "show it": a repeated tour is a smaller
    // annoyance than one that can never run.
    return false;
  }
}

export function rememberTour() {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Nothing to do — the tour simply runs again next time.
  }
}

export function forgetTour() {
  try {
    localStorage.removeItem(SEEN_KEY);
  } catch {
    /* empty */
  }
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function measure(selector: string): Box | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

export function Tour({ onClose, onTab }: { onClose: () => void; onTab: (tab: Tab) => void }) {
  const [step, setStep] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const current = STEPS[step];

  // The highlighted element moves when the window is resized and when the
  // layout switches between side-by-side and stacked, so the rectangle is
  // measured from the live DOM rather than remembered.
  useEffect(() => {
    const tab = STEPS[step].tab;
    if (tab) onTab(tab);
    // Measured after the tab switch, since that is what decides the layout
    // the rectangle is being taken from.
    const update = () => setBox(measure(STEPS[step].target));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
    // `onTab` is App's own setState, which React guarantees is stable, so
    // depending on it costs nothing and keeps the rule satisfied honestly.
  }, [step, onTab]);

  function finish() {
    rememberTour();
    onClose();
  }

  function next() {
    if (step + 1 >= STEPS.length) finish();
    else setStep(step + 1);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const CARD = 320;
  const GAP = 14;

  /** Placed so that it never covers what it is describing: beside a target
   *  that sits on the right half of the screen (there is map to spare on the
   *  left), and otherwise below it, or above it when there is no room below. */
  function placeCard(b: Box | null): React.CSSProperties {
    if (!b) return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };

    const beside = b.left > window.innerWidth / 2;
    const left = beside
      ? Math.max(12, b.left - GAP - CARD)
      : Math.max(12, Math.min(b.left, window.innerWidth - CARD - 12));

    if (beside) return { top: Math.max(12, b.top), left };

    const below = b.top + b.height + GAP;
    return below < window.innerHeight - 190
      ? { top: below, left }
      : { bottom: window.innerHeight - b.top + GAP, left };
  }

  const cardStyle = placeCard(box);

  // The body text varies in length, so the card's own height decides whether
  // it fits: a step whose card ran off the bottom of the window would hide its
  // own buttons. Measured after paint and nudged up, rather than guessed at.
  //
  // `step` and `box` are change triggers rather than values this effect reads
  // — a new step or a moved highlight means re-measure — which the exhaustive
  // deps rule cannot express, so it is disabled here deliberately.
  /* oxlint-disable react/exhaustive-effect-dependencies */
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const overflow = r.bottom - (window.innerHeight - 12);
    if (overflow > 0) el.style.top = `${Math.max(12, r.top - overflow)}px`;
  }, [step, box]);
  /* oxlint-enable react/exhaustive-effect-dependencies */

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label="Quick tour">
      {box && (
        <div
          className="tour-hole"
          style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
        />
      )}

      <div className="tour-card" ref={cardRef} style={cardStyle}>
        <div className="tour-step">
          Step {step + 1} of {STEPS.length}
        </div>
        <h3>{current.title}</h3>
        <p>{current.body}</p>
        <div className="tour-actions">
          <button type="button" className="tour-skip" onClick={finish}>
            Skip
          </button>
          <button type="button" className="tour-next" onClick={next}>
            {step + 1 === STEPS.length ? "Start exploring" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
