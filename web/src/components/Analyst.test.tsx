import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Analyst } from "./Analyst";
import type { Selection } from "../types";
import { dataset } from "../test/fixtures";

const data = dataset();
const noop = () => {};

function stubChat(response: unknown, { ok = true, status = 200 } = {}) {
  const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
    void init;
    return {
      ok,
      status,
      json: async () => response,
      text: async () => JSON.stringify(response),
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The JSON body the component posted on its nth call to /api/chat. */
function postedBody(fetchMock: ReturnType<typeof stubChat>, call = 0) {
  return JSON.parse(String(fetchMock.mock.calls[call][1].body));
}

/** `open` belongs to the caller in the real app, so the tests drive the same
 *  contract through a minimal host instead of asserting against a mode the
 *  product does not have. */
function Host({
  selection = null,
  onSelect = noop,
}: {
  selection?: Selection;
  onSelect?: (s: Selection) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Analyst
      data={data}
      onSelect={onSelect}
      selection={selection}
      open={open}
      onOpenChange={setOpen}
    />
  );
}

function renderDock(selection: Selection = null, onSelect: (s: Selection) => void = noop) {
  return render(<Host selection={selection} onSelect={onSelect} />);
}

/** One of the starter questions, which is all the empty column now holds. */
const SUGGESTION = "Which branches are most at risk, and why?";

const field = () => screen.getByPlaceholderText(/^Ask about/);
const launcher = () => screen.getByRole("button", { name: /^Ask / });

/** The column is closed until the reader asks for it, so most tests start by
 *  opening it the way a user does: clicking the launcher over the map. */
async function openDock() {
  await userEvent.click(launcher());
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Analyst when closed", () => {
  it("offers a launcher instead of a tab, and nothing else", () => {
    // No tab to find, no panel taking room until it is wanted.
    renderDock();
    expect(screen.getByRole("button", { name: "Ask the analyst" })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/^Ask about/)).not.toBeInTheDocument();
    expect(screen.queryByText(SUGGESTION)).not.toBeInTheDocument();
  });

  it("does not let the launcher imply the chat is scoped to the selection", async () => {
    // The analyst answers network-wide questions whatever is selected, so the
    // door into it says so.
    renderDock({ kind: "branch", id: "BD02" });
    expect(screen.getByRole("button", { name: "Ask the analyst" })).toBeInTheDocument();
  });

  it("opens the column when the launcher is clicked", async () => {
    renderDock();
    await openDock();
    expect(screen.getByText(SUGGESTION)).toBeInTheDocument();
    expect(field()).toBeInTheDocument();
  });

  it("closes on Escape, the way any transient surface should", async () => {
    renderDock();
    await openDock();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByText(SUGGESTION)).not.toBeInTheDocument();
  });

  it("can be closed again without losing the transcript", async () => {
    stubChat({ answer: "Al Warqa (BD02) is the weakest.", tools: [] });
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(screen.getByText(/is the weakest/)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Close the analyst" }));
    expect(screen.queryByText(/is the weakest/)).not.toBeInTheDocument();

    await openDock();
    expect(screen.getByText(/is the weakest/)).toBeInTheDocument();
  });
});

describe("Analyst before any question", () => {
  it("opens on the starter questions and nothing else to read", async () => {
    // The column is for the conversation. How the analyst works is a claim for
    // the How tab and the README, not a wall of prose over the input.
    renderDock();
    await openDock();
    expect(screen.getByText(SUGGESTION)).toBeInTheDocument();
    expect(screen.queryByText(/vector store/)).not.toBeInTheDocument();
    expect(screen.queryByText(/calling tools/)).not.toBeInTheDocument();
  });

  it("offers starter questions", async () => {
    renderDock();
    await openDock();
    expect(screen.getByText("Which branches are most at risk, and why?")).toBeInTheDocument();
  });

  it("disables the submit button until something is typed", async () => {
    renderDock();
    await openDock();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await userEvent.type(field(), "hello");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });
});

describe("Analyst and the current selection", () => {
  it("offers the selection as context without claiming to be limited to it", async () => {
    // So the reader can see that "why this one?" will resolve to something,
    // and equally that a network-wide question is still fair game.
    renderDock({ kind: "branch", id: "BD02" });
    await openDock();
    expect(screen.getByText(/is selected/)).toHaveTextContent("Bedashing Beta");
    expect(screen.getByText(/Everything else is still answerable/)).toBeInTheDocument();
    // The box asks for questions, not for questions about one lounge.
    expect(screen.getByPlaceholderText("Ask about the network…")).toBeInTheDocument();
  });

  it("lets the reader detach the context, and then stops sending it", async () => {
    const fetchMock = stubChat({ answer: "ok", tools: [] });
    renderDock({ kind: "branch", id: "BD02" });
    await openDock();

    await userEvent.click(
      screen.getByRole("button", { name: "Stop sending the selection as context" }),
    );
    expect(screen.queryByText(/is selected/)).not.toBeInTheDocument();

    await userEvent.type(field(), "which branches are strongest?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(postedBody(fetchMock).context).toBeUndefined();
  });

  it("leads with a question about the selected branch", async () => {
    renderDock({ kind: "branch", id: "BD02" });
    await openDock();
    expect(screen.getByText("Why this recommendation for Bedashing Beta?")).toBeInTheDocument();
  });

  it("re-offers the context when the reader points at something else", async () => {
    // Dismissing means "not about that one", not "never again": the next
    // thing they click is a fresh intent.
    const { rerender } = renderDock({ kind: "branch", id: "BD02" });
    await openDock();
    await userEvent.click(
      screen.getByRole("button", { name: "Stop sending the selection as context" }),
    );
    expect(screen.queryByText(/is selected/)).not.toBeInTheDocument();

    rerender(<Host selection={{ kind: "zone", id: "871e1d0ffffffff" }} />);
    expect(screen.getByText(/is selected/)).toHaveTextContent("candidate zone");
  });

  it("says nothing about context when nothing is selected", async () => {
    renderDock();
    await openDock();
    expect(screen.getByPlaceholderText("Ask about the network…")).toBeInTheDocument();
    expect(screen.queryByText(/is selected/)).not.toBeInTheDocument();
  });
});

describe("Analyst asking a question", () => {
  it("posts the transcript and renders the answer", async () => {
    const fetchMock = stubChat({ answer: "Al Warqa (BD02) is the weakest.", tools: [] });
    renderDock();
    await openDock();

    await userEvent.type(field(), "who is weakest?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByText(/is the weakest/)).toBeInTheDocument());
    const body = postedBody(fetchMock);
    expect(body.messages).toEqual([{ role: "user", content: "who is weakest?" }]);
  });

  it("submits on Enter, not only through the button", async () => {
    stubChat({ answer: "Answered.", tools: [] });
    renderDock();
    await openDock();
    await userEvent.type(field(), "anything{Enter}");
    await waitFor(() => expect(screen.getByText("Answered.")).toBeInTheDocument());
  });

  it("sends a starter question straight through", async () => {
    stubChat({ answer: "Answered.", tools: [] });
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Best whitespace in Dubai right now?"));
    await waitFor(() => expect(screen.getByText("Answered.")).toBeInTheDocument());
  });

  it("tells the endpoint what the user is currently looking at", async () => {
    // So that "why this one?" resolves without the user naming the branch.
    const fetchMock = stubChat({ answer: "ok", tools: [] });
    renderDock({ kind: "branch", id: "BD02" });
    await openDock();
    await userEvent.type(field(), "why this one?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = postedBody(fetchMock);
    expect(body.context).toEqual({ selected_branch_id: "BD02" });
  });

  it("passes a selected zone as context too", async () => {
    const fetchMock = stubChat({ answer: "ok", tools: [] });
    renderDock({ kind: "zone", id: "871e1d0ffffffff" });
    await openDock();
    await userEvent.type(field(), "and here?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(postedBody(fetchMock).context).toEqual({
      selected_zone_id: "871e1d0ffffffff",
    });
  });

  it("shows the tool trace so the answer can be audited", async () => {
    // The difference between a grounded answer and a fluent one is whether
    // the numbers were looked up. The trace is the evidence.
    stubChat({
      answer: "BD02 is weakest.",
      tools: [
        {
          name: "list_branches",
          arguments: { sort_by: "strength" },
          result_summary: '{"total_matching":3}',
        },
      ],
    });
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));

    await waitFor(() => expect(screen.getByText(/1 tool call/)).toBeInTheDocument());
    // Named in the summary line and again in the expandable payload.
    expect(screen.getAllByText(/list_branches/).length).toBeGreaterThan(1);
    expect(screen.getByText(/total_matching/)).toBeInTheDocument();
  });

  it("turns branch ids in the answer into map navigation", async () => {
    const onSelect = vi.fn();
    stubChat({ answer: "Look at Al Warqa (BD02) first.", tools: [] });
    renderDock(null, onSelect);
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));

    const link = await screen.findByRole("button", { name: "BD02" });
    await userEvent.click(link);
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD02" });
  });

  it("leaves an unknown id as plain text", async () => {
    stubChat({ answer: "Also BD99 maybe.", tools: [] });
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(screen.getByText(/Also BD99 maybe/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "BD99" })).not.toBeInTheDocument();
  });
});

describe("Analyst error handling", () => {
  async function ask(response: unknown, status: number) {
    stubChat(response, { ok: false, status });
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
  }

  it("explains the missing key on a 501 and says the rest still works", async () => {
    await ask({ error: "no key" }, 501);
    await waitFor(() =>
      expect(screen.getByText(/needs an OPENAI_API_KEY on the server/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/works without it/)).toBeInTheDocument();
  });

  it("explains that a 404 means the Pages Function is not being served", async () => {
    // The dock is always visible, so `npm run dev` users will meet this
    // endpoint constantly; the status code alone tells them nothing.
    await ask({ error: "not found" }, 404);
    await waitFor(() => expect(screen.getByText(/wrangler pages dev/)).toBeInTheDocument());
    expect(screen.getByText(/does not run Pages Functions/)).toBeInTheDocument();
  });

  it("reports any other status with its body", async () => {
    await ask({ error: "upstream exploded" }, 502);
    await waitFor(() => expect(screen.getByText(/returned 502/)).toBeInTheDocument());
  });

  it("explains that npm run dev has no Pages Function when the fetch fails", async () => {
    // The most likely confusion for a reviewer running the app locally.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Failed to fetch");
      }),
    );
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(screen.getByText(/wrangler pages dev/)).toBeInTheDocument());
    expect(screen.getByText(/rest of the product does not need it/)).toBeInTheDocument();
  });

  it("re-enables the input after a failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("boom");
      }),
    );
    renderDock();
    await openDock();
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(field()).toBeEnabled());
  });

  it("ignores an empty submission", async () => {
    const fetchMock = stubChat({ answer: "x", tools: [] });
    renderDock();
    await openDock();
    await userEvent.type(field(), "   {Enter}");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
