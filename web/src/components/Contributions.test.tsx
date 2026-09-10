import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContributionBreakdown } from "./Contributions";
import { axis, contribution } from "../test/fixtures";

/** The explainability centrepiece.
 *
 *  A reviewer's four questions are "why this recommendation", "what drove it",
 *  "what were the inputs" and "where should I be careful". This component
 *  answers the first three, so these tests are about whether it actually does
 *  — not about markup.
 */

const props = {
  title: "Why — branch strength",
  hint: "How well this lounge performs as a business.",
};

describe("ContributionBreakdown", () => {
  it("shows the axis score in the header", () => {
    const { container } = render(<ContributionBreakdown axis={axis()} {...props} />);
    expect(container.querySelector(".section-head .score")?.textContent).toBe("0.330");
  });

  it("orders rows by absolute impact, not by sign or by input order", () => {
    // "What inputs most influenced the outcome?" is answered by ordering, so a
    // large negative driver must appear above a small positive one.
    render(
      <ContributionBreakdown
        axis={axis({
          contributions: [
            contribution({ signal: "small", label: "Small positive", contribution: 0.02 }),
            contribution({ signal: "big", label: "Big negative", contribution: -0.3 }),
            contribution({ signal: "mid", label: "Middling", contribution: 0.15 }),
          ],
        })}
        {...props}
      />,
    );
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels[0]).toContain("Big negative");
    expect(labels[1]).toContain("Middling");
    expect(labels[2]).toContain("Small positive");
  });

  it("can preserve the model's own ordering when asked", () => {
    render(
      <ContributionBreakdown
        axis={axis({
          contributions: [
            contribution({ signal: "small", label: "Small positive", contribution: 0.02 }),
            contribution({ signal: "big", label: "Big negative", contribution: -0.3 }),
          ],
        })}
        sortByImpact={false}
        {...props}
      />,
    );
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels[0]).toContain("Small positive");
  });

  it("renders negative contributions with their sign and a down direction", () => {
    const { container } = render(
      <ContributionBreakdown
        axis={axis({
          contributions: [
            contribution({
              signal: "cannibalisation_penalty",
              label: "Self-cannibalisation",
              contribution: -0.09,
            }),
          ],
        })}
        {...props}
      />,
    );
    const value = container.querySelector(".contrib-value");
    expect(value?.textContent).toBe("-0.090");
    expect(value?.className).toContain("down");
  });

  it("draws the bar on the negative side for a penalty", () => {
    const { container } = render(
      <ContributionBreakdown
        axis={axis({
          contributions: [contribution({ contribution: -0.2 })],
        })}
        {...props}
      />,
    );
    // Centred on zero: a penalty must fill leftwards, so "pushed the score
    // down" is legible without reading the number.
    expect(container.querySelector(".contrib-fill.down")).toBeTruthy();
    expect(container.querySelector(".contrib-fill.up")).toBeFalsy();
  });

  it("scales bars against the largest contribution in the group", () => {
    const { container } = render(
      <ContributionBreakdown
        axis={axis({
          contributions: [
            contribution({ signal: "a", contribution: 0.4 }),
            contribution({ signal: "b", contribution: 0.2 }),
          ],
        })}
        {...props}
      />,
    );
    const fills = [...container.querySelectorAll<HTMLElement>(".contrib-fill")];
    expect(fills[0].style.width).toBe("50%");
    expect(fills[1].style.width).toBe("25%");
  });

  it("shows the raw value and the arithmetic without being expanded", () => {
    render(<ContributionBreakdown axis={axis()} {...props} />);
    expect(screen.getAllByText("4.6★").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/norm 0\.67 × w \+0\.30/).length).toBeGreaterThan(0);
  });

  it("hides the reasoning until a row is opened", async () => {
    const explanation = "Normalised against the band the market actually occupies.";
    render(
      <ContributionBreakdown
        axis={axis({ contributions: [contribution({ explanation })] })}
        {...props}
      />,
    );
    expect(screen.queryByText(explanation)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText(explanation)).toBeInTheDocument();
  });

  it("opens a row from the keyboard", async () => {
    const explanation = "Reachable without a mouse.";
    render(
      <ContributionBreakdown
        axis={axis({ contributions: [contribution({ explanation })] })}
        {...props}
      />,
    );
    screen.getByRole("button").focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByText(explanation)).toBeInTheDocument();
  });

  it("prints the sum of contributions so the reader can check it", () => {
    // The product's claim is that the breakdown *is* the model. Showing the
    // sum invites the reviewer to verify that rather than take it on trust.
    const { container } = render(
      <ContributionBreakdown
        axis={axis({
          contributions: [
            contribution({ signal: "a", contribution: 0.3 }),
            contribution({ signal: "b", contribution: -0.1 }),
          ],
        })}
        {...props}
      />,
    );
    expect(screen.getByText("sum of contributions")).toBeInTheDocument();
    expect(container.querySelector(".contrib-total")?.textContent).toContain("0.200");
  });

  it("the printed sum equals the displayed score", () => {
    const a = axis({
      contributions: [
        contribution({ signal: "a", contribution: 0.25 }),
        contribution({ signal: "b", contribution: -0.05 }),
      ],
    });
    render(<ContributionBreakdown axis={a} {...props} />);
    // Both the header score and the footer total render 0.200.
    expect(screen.getAllByText("0.200")).toHaveLength(2);
  });

  it("shows the axis hint so the reader knows what the score is for", () => {
    render(<ContributionBreakdown axis={axis()} {...props} />);
    expect(screen.getByText(props.hint)).toBeInTheDocument();
  });
});
