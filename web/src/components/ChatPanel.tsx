import { useEffect, useRef, useState } from "react";
import type { Dataset, Selection } from "../types";

/** The conversational analyst.
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
  role: "user" | "assistant";
  content: string;
  tools?: ToolCall[];
  error?: boolean;
}

const SUGGESTIONS = [
  "Which branches are most at risk, and why?",
  "Where are we competing with ourselves the most?",
  "Best whitespace in Dubai right now?",
  "Compare Khalifa City with Palm Jumeirah.",
  "If I could only close one lounge, which and what would I lose?",
];

/** Turn any branch or zone id the answer mentions into a click that moves the
 *  map. The analyst and the map should be one product, not two. */
function linkify(
  text: string,
  data: Dataset,
  onSelect: (s: Selection) => void,
): React.ReactNode[] {
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

export function ChatPanel({
  data,
  onSelect,
  selection,
}: {
  data: Dataset;
  onSelect: (s: Selection) => void;
  selection: Selection;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;

    const next: Msg[] = [...messages, { role: "user", content: question }];
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
          context:
            selection?.kind === "branch"
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
            role: "assistant",
            content:
              res.status === 501
                ? "The live analyst needs an OPENAI_API_KEY on the server. Everything else on this page — the scores, the recommendations and the pre-generated analyst notes — is committed static data and works without it."
                : `The analyst endpoint returned ${res.status}. ${body.slice(0, 300)}`,
            error: true,
          },
        ]);
        return;
      }

      const payload = (await res.json()) as { answer: string; tools: ToolCall[] };
      setMessages([
        ...next,
        { role: "assistant", content: payload.answer, tools: payload.tools },
      ]);
    } catch (err) {
      setMessages([
        ...next,
        {
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

  return (
    <div className="chat">
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <>
            <p className="hint" style={{ marginBottom: 4 }}>
              Ask the network analyst. It answers by calling tools over the same committed data
              this map renders — <code>list_branches</code>, <code>get_branch</code>,{" "}
              <code>compare_branches</code>, <code>find_overlaps</code>,{" "}
              <code>top_whitespace</code>, <code>network_summary</code> — and the trace of every
              call is shown with the answer.
            </p>
            <p className="hint">
              Deliberately no vector store: {data.branches.length} branches and{" "}
              {data.zones.length.toLocaleString()} scored cells are small and fully structured, so
              function calls are both more precise and more auditable than retrieval over
              embeddings.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button className="suggestion" key={s} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </>
        )}

        {messages.map((m, i) => (
          <div className={`msg msg-${m.role}`} key={i}>
            <div className="msg-role">{m.role === "user" ? "You" : "Network analyst"}</div>
            <div
              className="msg-body"
              style={m.error ? { color: "var(--hold)" } : undefined}
            >
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
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the network…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
