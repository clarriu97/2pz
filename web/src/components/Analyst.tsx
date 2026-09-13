import { useEffect, useRef, useState } from "react";
import type { Dataset, Selection } from "../types";

/** The conversational analyst, as its own column.
 *
 *  It used to be a tab, which hid the most differentiating part of the product
 *  behind a word ("Analyst") that reads like another report. Now a launcher
 *  sits over the map at all times, and opening it adds a third column: the map
 *  gives up width (it is elastic, and re-centres itself), while the breakdown
 *  the reader was studying stays exactly where it was. Nothing is covered —
 *  an overlay would have hidden the very numbers the answer is about.
 *
 *  The browser holds no key and no model logic: it posts the transcript to
 *  /api/chat, a Cloudflare Pages Function that runs the tool-calling loop
 *  against the same static JSON this page is rendering. The tool trace comes
 *  back with the answer and is shown collapsed under it, so a reviewer can
 *  check that the analyst actually looked the numbers up rather than recalled
 *  them — which is the difference between a grounded answer and a fluent one. */

interface ToolCall {
  name: string;
  arguments: unknown;
  result_summary: string;
}

interface Msg {
  /** Stable identity for React. The transcript is append-only, so an index
   *  would work today and break the moment anything edits or removes a turn. */
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: ToolCall[];
  error?: boolean;
}

let messageCounter = 0;
const nextId = () => `m${++messageCounter}`;

const SUGGESTIONS = [
  "Which branches are most at risk, and why?",
  "Where are we competing with ourselves the most?",
  "Best whitespace in Dubai right now?",
  "Compare Khalifa City with Palm Jumeirah.",
  "If I could only close one lounge, which and what would I lose?",
];

/** Turn any branch or zone id the answer mentions into a click that moves the
 *  map. The analyst and the map should be one product, not two. */
function linkify(text: string, data: Dataset, onSelect: (s: Selection) => void): React.ReactNode[] {
  const ids = new Map<string, Selection>();
  for (const b of data.branches) ids.set(b.branch_id, { kind: "branch", id: b.branch_id });
  const pattern = /\b(BD\d{2})\b/g;

  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = pattern.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const sel = ids.get(m[1]);
    const branch = data.branches.find((b) => b.branch_id === m![1]);
    out.push(
      sel ? (
        <button
          key={`l${k++}`}
          onClick={() => onSelect(sel)}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--accent)",
            textDecoration: "underline",
            textDecorationStyle: "dotted",
          }}
          title={branch?.name}
        >
          {m[1]}
        </button>
      ) : (
        m[1]
      ),
    );
    last = m.index + m[1].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** What the analyst will be told the reader is looking at, phrased for the
 *  reader rather than as an id. Showing it next to the input is what makes
 *  "why this one?" a sensible thing to type. */
function contextLabel(selection: Selection, data: Dataset): string | null {
  if (selection?.kind === "branch") {
    return data.branches.find((b) => b.branch_id === selection.id)?.name ?? null;
  }
  if (selection?.kind === "zone") {
    const zone = data.zones.find((z) => z.zone_id === selection.id);
    return zone ? `candidate zone · ${zone.metro}` : null;
  }
  return null;
}

function ChatIcon() {
  return (
    <svg className="analyst-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v6A1.5 1.5 0 0 1 12.5 11H6.8L3.6 13.6A.5.5 0 0 1 2.8 13.2V11h-.3A1.5 1.5 0 0 1 1 9.5v-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** `open` is owned by the caller because it changes the page layout: the grid
 *  above has to know whether there are two columns or three. */
export function Analyst({
  data,
  onSelect,
  selection,
  open,
  onOpenChange,
}: {
  data: Dataset;
  onSelect: (s: Selection) => void;
  selection: Selection;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  /** The selection whose context the reader dismissed. Keyed rather than a
   *  boolean so that picking something else re-offers it: dismissing means
   *  "not about that one", not "never mention what I am looking at". */
  const [dismissed, setDismissed] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // `messages` and `busy` are change triggers rather than values this effect
  // reads: a new turn or the thinking indicator appearing should scroll the
  // log to the bottom. The exhaustive-deps rule cannot express that
  // distinction, so it is disabled here deliberately rather than worked
  // around by moving the scroll into every call site.
  /* oxlint-disable react/exhaustive-effect-dependencies */
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);
  /* oxlint-enable react/exhaustive-effect-dependencies */

  // Opening the column is an explicit "I want to ask something", so the caret
  // should already be where the reader is about to type.
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;

    const next: Msg[] = [...messages, { id: nextId(), role: "user", content: question }];
    setMessages(next);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: next.map((m) => ({ role: m.role, content: m.content })),
          // Tell the analyst what the user is currently looking at, so
          // "why this one?" resolves without them having to name it.
          // Only what the reader can see attached, so the chip is the whole
          // truth about what the endpoint is told.
          context: !context
            ? undefined
            : selection?.kind === "branch"
              ? { selected_branch_id: selection.id }
              : selection?.kind === "zone"
                ? { selected_zone_id: selection.id }
                : undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.text();
        setMessages([
          ...next,
          {
            id: nextId(),
            role: "assistant",
            content:
              res.status === 501
                ? "The live analyst needs an OPENAI_API_KEY on the server. Everything else on this page — the scores, the recommendations and the pre-generated analyst notes — is committed static data and works without it."
                : res.status === 404
                  ? "There is no /api/chat here. Local `npm run dev` serves the app with Vite, which does not run Pages Functions — use `npx wrangler pages dev dist` (see the README) or the hosted link. The rest of the product does not need it."
                  : `The analyst endpoint returned ${res.status}. ${body.slice(0, 300)}`,
            error: true,
          },
        ]);
        return;
      }

      const payload = (await res.json()) as { answer: string; tools: ToolCall[] };
      setMessages([
        ...next,
        { id: nextId(), role: "assistant", content: payload.answer, tools: payload.tools },
      ]);
    } catch (err) {
      setMessages([
        ...next,
        {
          id: nextId(),
          role: "assistant",
          content:
            "Could not reach /api/chat. In local `npm run dev` there is no Pages Function — " +
            "run `npx wrangler pages dev` (see the README) or use the hosted link. The rest of " +
            "the product does not need it.\n\n" +
            String(err),
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const selectionKey = selection ? `${selection.kind}:${selection.id}` : null;
  const context = dismissed === selectionKey ? null : contextLabel(selection, data);
  // With something selected, the most useful question is about that thing, so
  // it leads the list instead of the generic network-wide openers.
  const suggestions =
    selection?.kind === "branch" && context
      ? [`Why this recommendation for ${context}?`, ...SUGGESTIONS.slice(0, 3)]
      : SUGGESTIONS;

  return (
    <>
      {!open && (
        <button
          type="button"
          className="analyst-launcher"
          onClick={() => onOpenChange(true)}
          title="Ask questions about this network in plain language"
        >
          <ChatIcon />
          <span>Ask the analyst</span>
        </button>
      )}

      {open && (
        <section className="analyst" aria-label="Network analyst">
          <div className="analyst-head">
            <ChatIcon />
            <strong>Network analyst</strong>
            <button
              type="button"
              className="analyst-close"
              onClick={() => onOpenChange(false)}
              aria-label="Close the analyst"
            >
              ✕
            </button>
          </div>

          {context && (
            <div className="analyst-context">
              <span>
                <b>{context}</b> is selected — ask “why this one?” and it knows what you mean.
                Everything else is still answerable.
              </span>
              <button
                type="button"
                onClick={() => setDismissed(selectionKey)}
                aria-label="Stop sending the selection as context"
                title="Stop sending the selection as context"
              >
                ✕
              </button>
            </div>
          )}

          <div className="chat-log" ref={logRef}>
            {messages.length === 0 && (
              <div className="suggestions">
                {suggestions.map((s) => (
                  <button className="suggestion" key={s} onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((m) => (
              <div className={`msg msg-${m.role}`} key={m.id}>
                <div className="msg-role">{m.role === "user" ? "You" : "Network analyst"}</div>
                <div className="msg-body" style={m.error ? { color: "var(--hold)" } : undefined}>
                  {m.role === "assistant" ? linkify(m.content, data, onSelect) : m.content}
                </div>
                {m.tools && m.tools.length > 0 && (
                  <details className="tool-trace">
                    <summary>
                      ▸ {m.tools.length} tool call{m.tools.length > 1 ? "s" : ""}:{" "}
                      {m.tools.map((t) => t.name).join(", ")}
                    </summary>
                    <pre>
                      {m.tools
                        .map(
                          (t) =>
                            `${t.name}(${JSON.stringify(t.arguments)})\n  → ${t.result_summary}`,
                        )
                        .join("\n\n")}
                    </pre>
                  </details>
                )}
              </div>
            ))}

            {busy && (
              <div className="msg msg-assistant">
                <div className="msg-role">Network analyst</div>
                <div className="msg-body" style={{ color: "var(--text-faint)" }}>
                  thinking and calling tools…
                </div>
              </div>
            )}
          </div>

          <form
            className="chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") onOpenChange(false);
              }}
              // Deliberately the same with or without a selection: the box
              // takes any question about the network, and saying otherwise
              // would be the same overstatement the context line used to make.
              placeholder="Ask about the network…"
              disabled={busy}
            />
            <button type="submit" disabled={busy || !input.trim()}>
              Ask
            </button>
          </form>
        </section>
      )}
    </>
  );
}
