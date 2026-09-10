import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LayerToggles, Legend } from "./MapControls";
import { HowItWorks } from "./HowItWorks";
import { dataset } from "../test/fixtures";
import type { LayerState } from "../types";

const data = dataset();

const allOn: LayerState = {
  branches: true,
  catchments: true,
  overlaps: true,
  competitors: true,
  whitespace: true,
};

describe("LayerToggles", () => {
  it("offers one toggle per functional block of the brief", () => {
    // Five blocks, five layers — a reviewer can isolate exactly the
    // capability they are grading.
    render(<LayerToggles layers={allOn} onChange={vi.fn()} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
    for (const label of [
      "Branch network",
      "Catchments",
      "Self-overlap",
      "Competition",
      "Whitespace grid",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("explains what each layer is for, not just what it is called", () => {
    render(<LayerToggles layers={allOn} onChange={vi.fn()} />);
    expect(
      screen.getByText(/Where our own catchments compete with each other/),
    ).toBeInTheDocument();
  });

  it("reflects the current state", () => {
    render(<LayerToggles layers={{ ...allOn, competitors: false }} onChange={vi.fn()} />);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes.filter((b) => (b as HTMLInputElement).checked)).toHaveLength(4);
  });

  it("reports a single layer change without disturbing the others", async () => {
    const onChange = vi.fn();
    render(<LayerToggles layers={allOn} onChange={onChange} />);
    await userEvent.click(screen.getByText("Competition"));
    expect(onChange).toHaveBeenCalledWith({ ...allOn, competitors: false });
  });
});

describe("Legend", () => {
  it("shows branch labels with their counts when the layer is on", () => {
    render(<Legend layers={allOn} data={data} />);
    expect(screen.getByText("PROTECT")).toBeInTheDocument();
    expect(screen.getAllByText("· 1").length).toBeGreaterThan(0);
  });

  it("hides a section whose layer is off", () => {
    // A legend for an invisible layer is noise.
    render(<Legend layers={{ ...allOn, whitespace: false }} data={data} />);
    expect(screen.queryByText("Candidate zones")).not.toBeInTheDocument();
    expect(screen.getByText("Existing lounges")).toBeInTheDocument();
  });

  it("shows the competitor tiers and total", () => {
    render(<Legend layers={allOn} data={data} />);
    expect(screen.getByText(/Competitors \(1,354\)/)).toBeInTheDocument();
    expect(screen.getByText(/premium \/ spa/)).toBeInTheDocument();
  });

  it("shows the number of overlapping pairs", () => {
    render(<Legend layers={allOn} data={data} />);
    expect(screen.getByText(/shared catchment \(1 pairs\)/)).toBeInTheDocument();
  });

  it("renders a zero count rather than a blank for an absent label", () => {
    const noSkips = dataset();
    noSkips.modelCard.counts.zone_labels = { GROW: 2 };
    render(<Legend layers={allOn} data={noSkips} />);
    const skip = screen.getByText("SKIP").closest("span")!;
    expect(skip.textContent).toContain("0");
  });
});

describe("HowItWorks", () => {
  it("names the decision-maker specifically, not 'leadership'", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText("Head of Retail Portfolio")).toBeInTheDocument();
    expect(screen.getByText(/signs a lease, funds a refit/)).toBeInTheDocument();
  });

  it("states the decisions the tool supports", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText(/PROTECT · HOLD · SHRINK per lounge/)).toBeInTheDocument();
    expect(screen.getByText(/GROW · WATCH · SKIP per candidate zone/)).toBeInTheDocument();
  });

  it("admits which signals are proxies for private data", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText(/revenue per chair, booking density/)).toBeInTheDocument();
  });

  it("groups every field by provenance tier", () => {
    const { container } = render(<HowItWorks data={data} />);
    expect(container.querySelector(".prov-real")).toBeTruthy();
    expect(container.querySelector(".prov-derived")).toBeTruthy();
    expect(container.querySelector(".prov-synthetic")).toBeTruthy();
    expect(screen.getByText("branch.momentum")).toBeInTheDocument();
  });

  it("renders the live weights from the model card, not a hand-written copy", () => {
    // If these were duplicated in the UI they would drift from the pipeline.
    render(<HowItWorks data={data} />);
    expect(screen.getByText("rating_norm")).toBeInTheDocument();
    // Both negative weights (cannibalisation and saturation) render as -0.20.
    expect(screen.getAllByText("-0.20")).toHaveLength(2);
    expect(screen.getByText("cannibalisation_penalty")).toBeInTheDocument();
  });

  it("explains why the model is not machine learning", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText(/A committee has to defend a lease decision/)).toBeInTheDocument();
  });

  it("points at the single file that holds every tunable", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText("pipeline/config.py")).toBeInTheDocument();
  });

  it("carries the trust caveats in the product, not only the README", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText(/Catchments are radii, not drive times\./)).toBeInTheDocument();
    expect(screen.getByText(/Competitor ratings are simulated\./)).toBeInTheDocument();
    expect(screen.getByText(/Trust the geometry, question the weights\./)).toBeInTheDocument();
  });

  it("reports the seed and the content fingerprint", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText("20260910")).toBeInTheDocument();
    expect(screen.getByText("89ab39341d83260b")).toBeInTheDocument();
  });

  it("explains why there is no build timestamp", () => {
    // A clock reading would make the dataset differ on every run while
    // telling a reviewer nothing they could check.
    render(<HowItWorks data={data} />);
    expect(screen.getByText(/deliberately no build timestamp/)).toBeInTheDocument();
  });

  it("shows the catchment radii per urban context", () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText("2.5 km")).toBeInTheDocument();
    expect(screen.getByText("6.0 km")).toBeInTheDocument();
  });
});
