import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Matrix } from "./Matrix";
import { dataset } from "../test/fixtures";

const data = dataset();
const noop = () => {};

/** The matrix has one job: make "strong branch, weak ground" visible. These
 *  tests pin the geometry that claim depends on — a chart whose axes are
 *  upside down or whose thresholds sit off-canvas would still render. */

function circles(container: HTMLElement) {
  return [...container.querySelectorAll<SVGCircleElement>("circle.matrix-point")];
}

describe("Matrix", () => {
  it("plots every branch", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    expect(circles(container)).toHaveLength(data.branches.length);
  });

  it("puts a higher market score higher on the chart", () => {
    // SVG y grows downward, so this is the assertion that catches a flipped
    // axis — which would invert the entire meaning of the picture.
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const byId = new Map(
      circles(container).map((c) => [c.getAttribute("aria-label")!, Number(c.getAttribute("cy"))]),
    );
    const high = [...byId.entries()].find(([label]) => label.startsWith("Al Ain"))![1];
    const low = [...byId.entries()].find(([label]) => label.startsWith("Al Warqa"))![1];
    // Al Ain has the higher market score in the fixture, so its y must be smaller.
    expect(high).toBeLessThan(low);
  });

  it("puts a higher strength score further right", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const points = circles(container).map((c) => ({
      label: c.getAttribute("aria-label")!,
      cx: Number(c.getAttribute("cx")),
    }));
    const strong = points.find((p) => p.label.startsWith("Mirdif"))!;
    const weak = points.find((p) => p.label.startsWith("Al Warqa"))!;
    expect(strong.cx).toBeGreaterThan(weak.cx);
  });

  it("keeps every threshold line inside the drawing area", () => {
    // Fitting the axes to the data alone could push a threshold off-canvas,
    // and the thresholds are the whole point of the chart.
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const svg = container.querySelector("svg")!;
    const [, , w, h] = svg.getAttribute("viewBox")!.split(" ").map(Number);
    for (const line of container.querySelectorAll<SVGLineElement>("line.matrix-threshold")) {
      for (const attr of ["x1", "x2"]) {
        const v = Number(line.getAttribute(attr));
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(w);
      }
      for (const attr of ["y1", "y2"]) {
        const v = Number(line.getAttribute(attr));
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(h);
      }
    }
  });

  it("keeps every branch inside the drawing area", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const svg = container.querySelector("svg")!;
    const [, , w, h] = svg.getAttribute("viewBox")!.split(" ").map(Number);
    for (const c of circles(container)) {
      expect(Number(c.getAttribute("cx"))).toBeGreaterThan(0);
      expect(Number(c.getAttribute("cx"))).toBeLessThan(w);
      expect(Number(c.getAttribute("cy"))).toBeGreaterThan(0);
      expect(Number(c.getAttribute("cy"))).toBeLessThan(h);
    }
  });

  it("sizes circles by review volume", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const points = circles(container).map((c) => ({
      label: c.getAttribute("aria-label")!,
      r: Number(c.getAttribute("r")),
    }));
    const big = points.find((p) => p.label.startsWith("Al Ain"))!; // 829 reviews
    const small = points.find((p) => p.label.startsWith("Al Warqa"))!; // 150 reviews
    expect(big.r).toBeGreaterThan(small.r);
  });

  it("colours each point by its recommendation", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    const fills = new Set(circles(container).map((c) => c.getAttribute("fill")));
    expect(fills.size).toBe(3);
  });

  it("draws the threshold values so they tie back to the config", () => {
    render(<Matrix data={data} selection={null} onSelect={noop} />);
    const t = data.modelCard.branch_model.thresholds;
    expect(screen.getByText(String(t.strength_high))).toBeInTheDocument();
    expect(screen.getByText(String(t.market_low))).toBeInTheDocument();
  });

  it("selects a branch when its point is clicked", async () => {
    const onSelect = vi.fn();
    const { container } = render(<Matrix data={data} selection={null} onSelect={onSelect} />);
    const mirdif = circles(container).find((c) =>
      c.getAttribute("aria-label")!.startsWith("Mirdif"),
    )!;
    await userEvent.click(mirdif);
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD01" });
  });

  it("labels and highlights the selected branch", () => {
    const { container } = render(
      <Matrix data={data} selection={{ kind: "branch", id: "BD02" }} onSelect={noop} />,
    );
    expect(container.querySelectorAll("circle.is-active")).toHaveLength(1);
    // Named twice on purpose: once as the point's label, once in the readout.
    expect(screen.getAllByText("Al Warqa").length).toBeGreaterThan(0);
  });

  it("reads out the selected branch's numbers", () => {
    render(<Matrix data={data} selection={{ kind: "branch", id: "BD02" }} onSelect={noop} />);
    const readout = document.querySelector(".matrix-readout")!;
    expect(readout.textContent).toContain("SHRINK");
    expect(readout.textContent).toContain("56% overlap");
  });

  it("explains the quadrants when nothing is selected", () => {
    render(<Matrix data={data} selection={null} onSelect={noop} />);
    expect(screen.getByText(/Top-right is PROTECT/)).toBeInTheDocument();
  });

  it("states why the picture exists", () => {
    // The chart's value is the argument it makes, not the dots.
    render(<Matrix data={data} selection={null} onSelect={noop} />);
    expect(screen.getByText(/cannibalisation, not underperformance/)).toBeInTheDocument();
  });

  it("gives every point an accessible description", () => {
    const { container } = render(<Matrix data={data} selection={null} onSelect={noop} />);
    for (const c of circles(container)) {
      expect(c.getAttribute("aria-label")).toMatch(/strength .*, market .*, (PROTECT|HOLD|SHRINK)/);
    }
  });
});
