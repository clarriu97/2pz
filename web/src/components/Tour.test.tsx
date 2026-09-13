import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { STEPS, Tour, forgetTour, hasSeenTour } from "./Tour";

/** jsdom has no layout engine: every getBoundingClientRect is zeroed, so the
 *  spotlight rectangle cannot be asserted here and is verified in a browser
 *  instead. What these tests guard is the part that can silently rot — the
 *  steps, the way out, and the promise not to show up twice. */

const noop = () => {};

/** Clicks through to the final step. A tour is sequential by definition, so
 *  these awaits belong in a loop. */
async function walkToLastStep() {
  for (let i = 0; i < STEPS.length - 1; i++) {
    // oxlint-disable-next-line no-await-in-loop
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
  }
}

beforeEach(() => {
  forgetTour();
});

afterEach(() => {
  forgetTour();
  vi.unstubAllGlobals();
});

describe("Tour steps", () => {
  it("opens on the first step and counts them honestly", () => {
    render(<Tour onClose={noop} onTab={noop} />);
    expect(screen.getByText(`Step 1 of ${STEPS.length}`)).toBeInTheDocument();
    expect(screen.getByText(STEPS[0].title)).toBeInTheDocument();
  });

  it("walks every step and ends on a finish button", async () => {
    render(<Tour onClose={noop} onTab={noop} />);
    await walkToLastStep();
    expect(screen.getByText(STEPS.at(-1)!.title)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start exploring" })).toBeInTheDocument();
  });

  it("opens the tab a step is about, so the panel behind it agrees", async () => {
    // A step describing Compare while the panel shows Why would teach the
    // wrong thing.
    const onTab = vi.fn();
    render(<Tour onClose={noop} onTab={onTab} />);
    await walkToLastStep();
    expect(onTab.mock.calls.map(([t]) => t)).toEqual(
      STEPS.map((s) => s.tab).filter((t): t is NonNullable<typeof t> => Boolean(t)),
    );
  });
});

describe("Tour dismissal", () => {
  it("remembers a completed tour", async () => {
    const onClose = vi.fn();
    render(<Tour onClose={onClose} onTab={noop} />);
    await walkToLastStep();
    await userEvent.click(screen.getByRole("button", { name: "Start exploring" }));
    expect(onClose).toHaveBeenCalled();
    expect(hasSeenTour()).toBe(true);
  });

  it("remembers a skipped tour too", async () => {
    // Skipping is an answer: asking again next visit would be nagging.
    const onClose = vi.fn();
    render(<Tour onClose={onClose} onTab={noop} />);
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onClose).toHaveBeenCalled();
    expect(hasSeenTour()).toBe(true);
  });

  it("closes on Escape, and counts that as seen", async () => {
    const onClose = vi.fn();
    render(<Tour onClose={onClose} onTab={noop} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
    expect(hasSeenTour()).toBe(true);
  });
});

describe("Tour storage", () => {
  it("treats unreadable storage as not seen rather than throwing", () => {
    // Private windows and blocked site data make localStorage throw on
    // access. A tutorial must never be why the page fails to load.
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    });
    expect(hasSeenTour()).toBe(false);
    expect(() => render(<Tour onClose={noop} onTab={noop} />)).not.toThrow();
  });

  it("survives a write it is not allowed to make", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {},
    });
    const onClose = vi.fn();
    render(<Tour onClose={onClose} onTab={noop} />);
    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onClose).toHaveBeenCalled();
  });
});
