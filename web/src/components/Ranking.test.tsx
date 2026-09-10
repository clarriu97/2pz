import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Ranking, TopZones } from "./Ranking";
import { dataset } from "../test/fixtures";

const data = dataset();
const noop = () => {};

function rowLabels() {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => r.querySelector("td")!.textContent);
}

describe("Ranking", () => {
  it("lists every branch by default", () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    expect(rowLabels()).toHaveLength(3);
  });

  it("sorts ascending by strength so the branches needing a decision are first", () => {
    // Which branch is "worst" depends on the question; the default answers
    // "who is weakest".
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    expect(rowLabels()[0]).toContain("Al Warqa");
  });

  it("reverses the sort when the same header is clicked twice", async () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    const first = rowLabels()[0];
    await userEvent.click(screen.getByTitle("Sort by Strength"));
    expect(rowLabels()[0]).not.toBe(first);
  });

  it("re-ranks on a different column", async () => {
    // The most cannibalised branch is a different branch from the weakest,
    // and a portfolio team needs both views.
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    await userEvent.click(screen.getByTitle("Sort by Overlap"));
    expect(rowLabels()[0]).toContain("Al Ain"); // 0% overlap, ascending
    await userEvent.click(screen.getByTitle("Sort by Overlap"));
    expect(rowLabels()[0]).toContain("Al Warqa"); // 56%, descending
  });

  it("sorts text columns alphabetically", async () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    await userEvent.click(screen.getByTitle("Sort by Lounge"));
    expect(rowLabels()[0]).toContain("Al Ain");
  });

  it("filters to a single recommendation", async () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    await userEvent.click(screen.getByText("SHRINK 1"));
    expect(rowLabels()).toHaveLength(1);
    expect(rowLabels()[0]).toContain("Al Warqa");
  });

  it("returns to the full list", async () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    await userEvent.click(screen.getByText("SHRINK 1"));
    await userEvent.click(screen.getByText("All 3"));
    expect(rowLabels()).toHaveLength(3);
  });

  it("opens a branch's breakdown when its row is clicked", async () => {
    const onSelect = vi.fn();
    render(<Ranking data={data} selection={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByText(/Al Warqa/));
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD02" });
  });

  it("marks the currently selected row", () => {
    render(<Ranking data={data} selection={{ kind: "branch", id: "BD02" }} onSelect={noop} />);
    const selected = screen
      .getAllByRole("row")
      .find((r) => r.getAttribute("aria-selected") === "true");
    expect(selected?.textContent).toContain("Al Warqa");
  });

  it("colours each row by its recommendation", () => {
    const { container } = render(<Ranking data={data} selection={null} onSelect={noop} />);
    const dots = [...container.querySelectorAll<HTMLElement>(".dot")];
    expect(dots).toHaveLength(3);
    expect(new Set(dots.map((d) => d.style.background)).size).toBe(3);
  });

  it("exposes every scored signal as a sortable column", () => {
    render(<Ranking data={data} selection={null} onSelect={noop} />);
    for (const header of ["Strength", "Market", "Rating", "Reviews", "Rivals", "Overlap"]) {
      expect(screen.getByTitle(`Sort by ${header}`)).toBeInTheDocument();
    }
  });
});

describe("TopZones", () => {
  it("ranks candidate zones by opportunity, highest first", () => {
    render(<TopZones data={data} onSelect={noop} />);
    const scores = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => Number(r.querySelectorAll("td")[1].textContent));
    expect(scores).toEqual(scores.toSorted((a, b) => b - a));
  });

  it("excludes foregone SKIPs from the shortlist", () => {
    const withSkip = dataset();
    withSkip.zones = [
      ...withSkip.zones,
      { ...withSkip.zones[0], zone_id: "skipme", recommendation: "SKIP" },
    ];
    render(<TopZones data={withSkip} onSelect={noop} />);
    expect(screen.queryByText("SKIP")).not.toBeInTheDocument();
  });

  it("opens a zone when its row is clicked", async () => {
    const onSelect = vi.fn();
    render(<TopZones data={data} onSelect={onSelect} />);
    await userEvent.click(screen.getAllByRole("row")[1]);
    expect(onSelect).toHaveBeenCalledWith({ kind: "zone", id: "871e1d0ffffffff" });
  });

  it("shows the coverage gap alongside the score", () => {
    // "6.8 km from the nearest lounge" is the fact that makes a score
    // actionable; the score alone is not.
    render(<TopZones data={data} onSelect={noop} />);
    expect(screen.getByText("6.8 km")).toBeInTheDocument();
  });
});
