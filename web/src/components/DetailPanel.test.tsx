import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DetailPanel } from "./DetailPanel";
import { dataset } from "../test/fixtures";

const data = dataset();
const noop = () => {};

describe("DetailPanel with nothing selected", () => {
  it("tells the reader what to click and what they will get", () => {
    render(<DetailPanel selection={null} data={data} onSelect={noop} />);
    expect(screen.getByText(/Click a lounge/)).toBeInTheDocument();
    expect(screen.getByText(/add up to the score exactly/)).toBeInTheDocument();
  });
});

describe("DetailPanel for a branch", () => {
  const selection = { kind: "branch", id: "BD01" } as const;

  it("leads with the recommendation and the rule that produced it", () => {
    // "Why did this branch get this recommendation?" must be answerable from
    // the top of the panel, not by inference.
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("HOLD")).toBeInTheDocument();
    expect(screen.getByText(/fall between the PROTECT and SHRINK thresholds/)).toBeInTheDocument();
  });

  it("shows both score axes with their breakdowns", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("Why — branch strength")).toBeInTheDocument();
    expect(screen.getByText("Why — market & defensibility")).toBeInTheDocument();
  });

  it("labels every input with where the number came from", () => {
    // The honesty claim: a reviewer never has to guess whether a figure is
    // measured, computed or simulated.
    const { container } = render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(container.querySelectorAll(".prov-real").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".prov-derived").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".prov-synthetic").length).toBeGreaterThan(0);
  });

  it("marks the simulated fields as synthetic, not the real ones", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    const momentum = screen.getByText("Momentum").closest("dt")!;
    expect(momentum.querySelector(".prov-synthetic")).toBeTruthy();
    const rating = screen.getByText("Rating").closest("dt")!;
    expect(rating.querySelector(".prov-real")).toBeTruthy();
  });

  it("shows the grounded analyst note with its model", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/shares 43% of its catchment/)).toBeInTheDocument();
    expect(screen.getByText(/gpt-4\.1-mini/)).toBeInTheDocument();
  });

  it("flags a stale note rather than passing it off as current", () => {
    // Notes are pre-generated, so they can fall behind a config change. The
    // one place this product could quietly mislead.
    render(<DetailPanel selection={{ kind: "branch", id: "BD02" }} data={data} onSelect={noop} />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("explains how to produce a note when one is missing", () => {
    render(<DetailPanel selection={{ kind: "branch", id: "BD03" }} data={data} onSelect={noop} />);
    expect(screen.getByText(/No pre-generated note/)).toBeInTheDocument();
    expect(screen.getByText("pipeline/ai/notes.py")).toBeInTheDocument();
  });

  it("lists the confidence caveats when there are any", () => {
    render(<DetailPanel selection={{ kind: "branch", id: "BD02" }} data={data} onSelect={noop} />);
    expect(screen.getByText("Only 150 reviews.")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
  });

  it("says so explicitly when there are no caveats", () => {
    // Silence would read as "not checked"; the panel states that it was.
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/No specific caveats/)).toBeInTheDocument();
  });

  it("shows the sibling overlap table and explains the union", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("Own-network overlap")).toBeInTheDocument();
    expect(
      screen.getByText(/three siblings covering the same corner are counted/),
    ).toBeInTheDocument();
    // Appears both as the section score and in the sibling row.
    expect(screen.getAllByText("43%").length).toBeGreaterThan(1);
  });

  it("omits the overlap section for an isolated branch", () => {
    render(<DetailPanel selection={{ kind: "branch", id: "BD03" }} data={data} onSelect={noop} />);
    expect(screen.queryByText("Own-network overlap")).not.toBeInTheDocument();
  });

  it("navigates to a sibling when its row is clicked", async () => {
    const onSelect = vi.fn();
    render(<DetailPanel selection={selection} data={data} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("Al Warqa"));
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD02" });
  });

  it("lists the nearest rivals", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("Nearest rivals")).toBeInTheDocument();
    expect(screen.getByText("Rival Beauty")).toBeInTheDocument();
  });

  it("reports a missing branch instead of rendering blank", () => {
    render(<DetailPanel selection={{ kind: "branch", id: "BD99" }} data={data} onSelect={noop} />);
    expect(screen.getByText("Branch not found.")).toBeInTheDocument();
  });
});

describe("DetailPanel for a zone", () => {
  const selection = { kind: "zone", id: "871e1d0ffffffff" } as const;

  it("leads with the label and the rule", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("GROW")).toBeInTheDocument();
    // Both the pill row and the decision rule quote the score.
    expect(screen.getAllByText(/opportunity 0\.47/).length).toBeGreaterThan(0);
  });

  it("shows the opportunity breakdown", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText("Why — opportunity score")).toBeInTheDocument();
  });

  it("says the demand figure is a proxy, not a census", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/not census population or income/)).toBeInTheDocument();
  });

  it("warns that a hex is a search area rather than a site", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/where to look, not where to sign/)).toBeInTheDocument();
  });

  it("explains that an uncovered cell is genuinely unserved", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/genuinely unserved by our network/)).toBeInTheDocument();
  });

  it("explains that a covered cell would move revenue rather than add it", () => {
    render(
      <DetailPanel
        selection={{ kind: "zone", id: "871e1d1ffffffff" }}
        data={data}
        onSelect={noop}
      />,
    );
    expect(screen.getByText(/move revenue rather than add it/)).toBeInTheDocument();
  });

  it("surfaces a non-residential flag as a caveat", () => {
    render(
      <DetailPanel
        selection={{ kind: "zone", id: "871e1d1ffffffff" }}
        data={data}
        onSelect={noop}
      />,
    );
    expect(screen.getByText(/commercial or industrial cell/)).toBeInTheDocument();
  });

  it("navigates to the nearest branch from the zone panel", async () => {
    const onSelect = vi.fn();
    render(<DetailPanel selection={selection} data={data} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("Bedashing Alpha"));
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD01" });
  });

  it("reports a missing zone", () => {
    render(<DetailPanel selection={{ kind: "zone", id: "nope" }} data={data} onSelect={noop} />);
    expect(screen.getByText("Zone not found.")).toBeInTheDocument();
  });
});

describe("DetailPanel for an overlap", () => {
  const selection = { kind: "overlap", id: "BD01~BD02" } as const;

  it("names both lounges and the shared area", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/Bedashing Alpha ∩ Bedashing Beta/)).toBeInTheDocument();
    expect(screen.getByText(/21\.6 km²/)).toBeInTheDocument();
  });

  it("ranks the branch that gives up more of its catchment first", () => {
    // The asymmetry is the decision: it says which of the two is the
    // consolidation candidate.
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Al Warqa");
    expect(rows[0].textContent).toContain("56%");
  });

  it("explains why the asymmetry matters", () => {
    render(<DetailPanel selection={selection} data={data} onSelect={noop} />);
    expect(screen.getByText(/Overlap is asymmetric/)).toBeInTheDocument();
  });

  it("navigates into a branch from the overlap panel", async () => {
    const onSelect = vi.fn();
    render(<DetailPanel selection={selection} data={data} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("Al Warqa"));
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD02" });
  });

  it("reports a missing overlap", () => {
    render(
      <DetailPanel selection={{ kind: "overlap", id: "BD09~BD10" }} data={data} onSelect={noop} />,
    );
    expect(screen.getByText("Overlap not found.")).toBeInTheDocument();
  });
});
