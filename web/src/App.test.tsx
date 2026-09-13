import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { dataset } from "./test/fixtures";
import { forgetTour, rememberTour } from "./components/Tour";

/** MapLibre draws to a WebGL canvas that jsdom cannot provide, so the map is
 *  replaced with a stub that records the props it was given. That is the right
 *  boundary: what matters here is whether App wires selection and layer state
 *  correctly, not whether MapLibre paints. */
const mapProps: Array<Record<string, unknown>> = [];

vi.mock("./components/MapView", () => ({
  MapView: (props: Record<string, unknown>) => {
    mapProps.push(props);
    return (
      <div data-testid="map">
        <button
          onClick={() => (props.onSelect as (s: unknown) => void)({ kind: "branch", id: "BD02" })}
        >
          simulate branch click
        </button>
        <button
          onClick={() =>
            (props.onSelect as (s: unknown) => void)({ kind: "zone", id: "871e1d0ffffffff" })
          }
        >
          simulate zone click
        </button>
      </div>
    );
  },
}));

const { default: App } = await import("./App");

const data = dataset();

function stubData(ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const name = url.split("/").pop()!;
      const files: Record<string, unknown> = {
        "branches.json": data.branches,
        "model_card.json": data.modelCard,
        "catchments.geojson": data.catchments,
        "overlaps.geojson": data.overlaps,
        "competitors.geojson": data.competitors,
        "whitespace.geojson": data.whitespace,
      };
      return { ok, status: ok ? 200 : 404, json: async () => files[name] };
    }),
  );
}

beforeEach(() => {
  mapProps.length = 0;
  // Every test below is about a returning visitor; the first-run tour has its
  // own tests, and an overlay over the whole app would be measuring it here.
  rememberTour();
});

afterEach(() => {
  vi.unstubAllGlobals();
  forgetTour();
});

describe("App loading", () => {
  it("shows a loading state before the data arrives", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<App />);
    expect(screen.getByText(/Loading network/)).toBeInTheDocument();
  });

  it("tells the reviewer how to generate the dataset if it is missing", async () => {
    // The most likely first-run failure, so the error is actionable rather
    // than a stack trace.
    stubData(false);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Could not load the dataset/)).toBeInTheDocument());
    expect(screen.getByText("uv run python -m pipeline.run")).toBeInTheDocument();
  });
});

describe("App header", () => {
  it("names the decision-maker it was built for", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByText("Head of Retail Portfolio")).toBeInTheDocument());
  });

  it("summarises the portfolio split in the header", async () => {
    stubData();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/1 protect · 1 hold · 1 shrink/)).toBeInTheDocument(),
    );
  });
});

describe("App default layers", () => {
  it("opens with the network readable rather than covered in points", async () => {
    // Thousands of competitor dots and a full hex grid on first paint would
    // hide the thing the reviewer came to see.
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    const layers = mapProps.at(-1)!.layers as Record<string, boolean>;
    expect(layers).toEqual({
      branches: true,
      catchments: true,
      overlaps: true,
      competitors: false,
      whitespace: false,
    });
  });

  it("passes a layer toggle down to the map", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByText("Competition"));
    await waitFor(() =>
      expect((mapProps.at(-1)!.layers as Record<string, boolean>).competitors).toBe(true),
    );
  });
});

describe("App selection", () => {
  it("shows the breakdown when the map reports a click", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByText("simulate branch click"));
    // Named in the detail heading and again on the analyst dock's context chip.
    expect(screen.getAllByText("Bedashing Beta").length).toBeGreaterThan(0);
    // The label appears on the detail pill and in the map legend.
    expect(screen.getAllByText("SHRINK").length).toBeGreaterThan(0);
    expect(screen.getByText("Why — branch strength")).toBeInTheDocument();
  });

  it("switches from a list back to the reasoning when a row is picked", async () => {
    // Otherwise the reader clicks a row and is left staring at the list they
    // just clicked out of.
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("tab", { name: "Compare" }));
    await userEvent.click(screen.getByText(/Al Warqa/));

    expect(screen.getByRole("tab", { name: "Why" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Why — branch strength")).toBeInTheDocument();
  });

  it("reveals the whitespace layer when a zone is selected", async () => {
    // Selecting a hex from the shortlist must not highlight something
    // invisible.
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByText("simulate zone click"));
    await waitFor(() =>
      expect((mapProps.at(-1)!.layers as Record<string, boolean>).whitespace).toBe(true),
    );
  });

  it("forwards the current selection to the map", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByText("simulate branch click"));
    await waitFor(() => expect(mapProps.at(-1)!.selection).toEqual({ kind: "branch", id: "BD02" }));
  });
});

describe("App first run", () => {
  it("runs the tour for a first-time visitor", async () => {
    forgetTour();
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: "Quick tour" })).toBeInTheDocument();
  });

  it("does not run it again once it has been seen", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    expect(screen.queryByRole("dialog", { name: "Quick tour" })).not.toBeInTheDocument();
  });

  it("can be replayed from the How tab, which is its only way back", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "How" }));
    await userEvent.click(screen.getByRole("button", { name: "Replay the tour" }));
    expect(screen.getByRole("dialog", { name: "Quick tour" })).toBeInTheDocument();
  });
});

describe("App tabs", () => {
  it("offers all four panels", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    for (const name of ["Why", "Compare", "Growth", "How"]) {
      expect(screen.getByRole("tab", { name })).toBeInTheDocument();
    }
  });

  it("opens the growth shortlist", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "Growth" }));
    expect(screen.getByText("Growth shortlist")).toBeInTheDocument();
  });

  it("opens the framing panel", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "How" }));
    expect(screen.getByText("Who this is for")).toBeInTheDocument();
  });

  it("keeps the analyst reachable from every tab rather than behind one", async () => {
    // It was a tab called "Analyst", which read like one more report and was
    // the least likely thing to be clicked. Now its launcher is on screen
    // whatever the panel is showing.
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: "Analyst" })).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: /^Ask / })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(screen.getByRole("button", { name: /^Ask / })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "How" }));
    expect(screen.getByRole("button", { name: /^Ask / })).toBeInTheDocument();
  });

  it("keeps the panel readable while the analyst is open", async () => {
    // The whole reason the analyst is a column and not an overlay: reading an
    // answer and reading the numbers it is about happen at the same time.
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /^Ask / }));
    expect(screen.getByPlaceholderText(/^Ask about/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Growth" }));
    expect(screen.getByText("Growth shortlist")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/^Ask about/)).toBeInTheDocument();
  });

  it("keeps the analyst open when a selection lands, next to the breakdown", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /^Ask / }));
    await userEvent.click(screen.getByText("simulate branch click"));
    expect(screen.getByText("Why — branch strength")).toBeInTheDocument();
    expect(screen.getByText(/is selected/)).toHaveTextContent("Bedashing Beta");
  });

  it("hands the analyst the branch the reader selected", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Ask the analyst" }));
    await userEvent.click(screen.getByText("simulate branch click"));
    expect(screen.getByText(/is selected/)).toHaveTextContent("Bedashing Beta");
  });
});
