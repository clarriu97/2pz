import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatPanel } from "./ChatPanel";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatPanel before any question", () => {
  it("states that answers come from tools over the committed data", () => {
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    expect(screen.getByText(/answers by calling tools/)).toBeInTheDocument();
    expect(screen.getByText("get_branch")).toBeInTheDocument();
  });

  it("justifies the absence of a vector store", () => {
    // Choosing not to reach for embeddings is a design decision, so the
    // product says so where a reviewer will read it.
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    expect(screen.getByText(/Deliberately no vector store/)).toBeInTheDocument();
  });

  it("offers starter questions", () => {
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    expect(screen.getByText("Which branches are most at risk, and why?")).toBeInTheDocument();
  });

  it("disables the submit button until something is typed", async () => {
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText(/Ask about the network/), "hello");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });
});

describe("ChatPanel asking a question", () => {
  it("posts the transcript and renders the answer", async () => {
    const fetchMock = stubChat({ answer: "Al Warqa (BD02) is the weakest.", tools: [] });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);

    await userEvent.type(screen.getByPlaceholderText(/Ask about the network/), "who is weakest?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByText(/is the weakest/)).toBeInTheDocument());
    const body = postedBody(fetchMock);
    expect(body.messages).toEqual([{ role: "user", content: "who is weakest?" }]);
  });

  it("sends a starter question straight through", async () => {
    stubChat({ answer: "Answered.", tools: [] });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Best whitespace in Dubai right now?"));
    await waitFor(() => expect(screen.getByText("Answered.")).toBeInTheDocument());
  });

  it("tells the endpoint what the user is currently looking at", async () => {
    // So that "why this one?" resolves without the user naming the branch.
    const fetchMock = stubChat({ answer: "ok", tools: [] });
    render(<ChatPanel data={data} onSelect={noop} selection={{ kind: "branch", id: "BD02" }} />);
    await userEvent.type(screen.getByPlaceholderText(/Ask about the network/), "why this one?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = postedBody(fetchMock);
    expect(body.context).toEqual({ selected_branch_id: "BD02" });
  });

  it("passes a selected zone as context too", async () => {
    const fetchMock = stubChat({ answer: "ok", tools: [] });
    render(
      <ChatPanel data={data} onSelect={noop} selection={{ kind: "zone", id: "871e1d0ffffffff" }} />,
    );
    await userEvent.type(screen.getByPlaceholderText(/Ask about the network/), "and here?");
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
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));

    await waitFor(() => expect(screen.getByText(/1 tool call/)).toBeInTheDocument());
    // Named in the summary line and again in the expandable payload.
    expect(screen.getAllByText(/list_branches/).length).toBeGreaterThan(1);
    expect(screen.getByText(/total_matching/)).toBeInTheDocument();
  });

  it("turns branch ids in the answer into map navigation", async () => {
    const onSelect = vi.fn();
    stubChat({ answer: "Look at Al Warqa (BD02) first.", tools: [] });
    render(<ChatPanel data={data} onSelect={onSelect} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));

    const link = await screen.findByRole("button", { name: "BD02" });
    await userEvent.click(link);
    expect(onSelect).toHaveBeenCalledWith({ kind: "branch", id: "BD02" });
  });

  it("leaves an unknown id as plain text", async () => {
    stubChat({ answer: "Also BD99 maybe.", tools: [] });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(screen.getByText(/Also BD99 maybe/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "BD99" })).not.toBeInTheDocument();
  });
});

describe("ChatPanel error handling", () => {
  it("explains the missing key on a 501 and says the rest still works", async () => {
    stubChat({ error: "no key" }, { ok: false, status: 501 });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() =>
      expect(screen.getByText(/needs an OPENAI_API_KEY on the server/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/works without it/)).toBeInTheDocument();
  });

  it("reports any other status with its body", async () => {
    stubChat({ error: "upstream exploded" }, { ok: false, status: 502 });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
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
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
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
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    await userEvent.click(screen.getByText("Which branches are most at risk, and why?"));
    await waitFor(() => expect(screen.getByPlaceholderText(/Ask about the network/)).toBeEnabled());
  });

  it("ignores an empty submission", async () => {
    const fetchMock = stubChat({ answer: "x", tools: [] });
    render(<ChatPanel data={data} onSelect={noop} selection={null} />);
    const input = screen.getByPlaceholderText(/Ask about the network/);
    await userEvent.type(input, "   {Enter}");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
