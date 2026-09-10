import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { dataset } from "./test/fixtures";

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
});

afterEach(() => {
  vi.unstubAllGlobals();
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
    expect(screen.getByText("Bedashing Beta")).toBeInTheDocument();
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

describe("App tabs", () => {
  it("offers all five panels", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    for (const name of ["Why", "Compare", "Growth", "Analyst", "How"]) {
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

  it("opens the analyst", async () => {
    stubData();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "Analyst" }));
    expect(screen.getByPlaceholderText(/Ask about the network/)).toBeInTheDocument();
  });
});
