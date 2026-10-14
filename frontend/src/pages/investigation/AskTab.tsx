import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { SignInChoices } from "../../auth/AccountMenu";
import { useAuth } from "../../auth/context";
import { SeverityBadge } from "../../components/Badges";
import { MiniMarkdown } from "../../components/MiniMarkdown";
import { fmtTimeMs } from "../../lib/format";
import { chatApi } from "../../services/api";
import type { ChatAgent, ChatMessage } from "../../types/account";
import type { InvestigationBundle, Severity } from "../../types/api";

const STARTERS = ["Give me an overview of this case", "What should I fix first?", "Is there anything wrong with authentication?", "Which findings were rejected and why?"];

function decidedLabel(m: ChatMessage): string {
  const d = m.decided_by ?? "";
  if (d.startsWith("llm:")) return d === "llm:cache" ? "model (cached)" : `answered by ${d.slice(4)}`;
  if (d === "policy-fallback") return "built from recorded results (model unavailable)";
  return "built from recorded results";
}

function AgentMessage({ m, onCite, onFollow, last, busy }: { m: ChatMessage; onCite: () => void; onFollow: (q: string) => void; last: boolean; busy: boolean }) {
  return (
    <div className="chat-msg agent">
      <div className="chat-who">
        <span className="chat-agent">{m.agent_display_name ?? m.agent}</span>
        <span className="small muted">{fmtTimeMs(m.created_at)}</span>
      </div>
      {m.routing_reason && (
        <div className="chat-route small muted" title={m.routed_by ? `routed by ${m.routed_by}` : undefined}>
          ↳ {m.routing_reason}
        </div>
      )}
      <MiniMarkdown text={m.content} />
      {m.citations.length > 0 && (
        <div className="chat-cites">
          <span className="small muted">Based on</span>
          {m.citations.slice(0, 5).map((c) => (
            <button key={c.finding_id} className="chat-cite" onClick={onCite} title={c.file ?? c.title}>
              <SeverityBadge severity={c.severity as Severity} />
              <span>{c.title}</span>
            </button>
          ))}
          {m.citations.length > 5 && <span className="small muted">+{m.citations.length - 5} more</span>}
        </div>
      )}
      <div className="small muted chat-foot">{decidedLabel(m)}</div>
      {last && m.follow_ups.length > 0 && (
        <div className="chat-follow">
          {m.follow_ups.map((q) => (
            <button key={q} className="chip-btn" disabled={busy} onClick={() => onFollow(q)}>
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AskTab({ data, onNavigate }: { data: InvestigationBundle; onNavigate: (tab: string) => void }) {
  const { user, config, loading } = useAuth();
  const id = data.detail.investigation_id;
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [agents, setAgents] = useState<ChatAgent[]>([]);
  const [agent, setAgent] = useState("");
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const running = ["queued", "running"].includes(data.detail.status);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    Promise.all([chatApi.history(id), chatApi.agents()])
      .then(([h, a]) => {
        if (!alive) return;
        setMessages(h.messages);
        setAgents(a);
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [id, user]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  async function ask(q: string) {
    const text = q.trim();
    if (!text || pending) return;
    setPending(text);
    setError(null);
    setQuestion("");
    try {
      const res = await chatApi.ask(id, text, agent || undefined);
      setMessages((prev) => [...(prev ?? []), res.question, res.answer]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setQuestion(text);
    } finally {
      setPending(null);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void ask(question);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (!user) {
    return (
      <div className="signin-card">
        <span className="eyebrow">Ask this case</span>
        <h2>Sign in to ask questions</h2>
        <p className="ink2">Each question goes to the agent responsible for the topic, which answers from its own findings and evidence. Your conversation is private to your account.</p>
        {config?.mode === "firebase" && <SignInChoices className="btn primary" />}
      </div>
    );
  }

  const empty = messages !== null && messages.length === 0;
  return (
    <div className="chat">
      <div className="chat-head">
        <div>
          <h2>Ask this case</h2>
          <p className="small ink2">
            Questions are routed to the agent that owns the topic (security, dependencies, licensing, verification, risk …). It answers only from what it recorded for{" "}
            <b>{data.detail.repository}</b> and cites the findings it used.
          </p>
        </div>
        {messages && messages.length > 0 && (
          <button
            className="btn sm quiet"
            disabled={Boolean(pending)}
            onClick={async () => {
              await chatApi.clear(id);
              setMessages([]);
            }}
          >
            Clear conversation
          </button>
        )}
      </div>
      {running && <div className="callout warn">The investigation is still running; answers cover what has been recorded so far.</div>}

      <div className="chat-log" aria-live="polite">
        {messages === null && !error && <p className="small muted">Loading conversation…</p>}
        {empty && (
          <div className="chat-empty">
            <p className="small muted">Try one of these:</p>
            <div className="chat-follow">
              {STARTERS.map((q) => (
                <button key={q} className="chip-btn" onClick={() => void ask(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {(messages ?? []).map((m, i) =>
          m.role === "user" ? (
            <div key={m.message_id} className="chat-msg user">
              <div className="chat-bubble">{m.content}</div>
            </div>
          ) : (
            <AgentMessage key={m.message_id} m={m} onCite={() => onNavigate("findings")} onFollow={(q) => void ask(q)} last={i === (messages?.length ?? 0) - 1} busy={Boolean(pending)} />
          ),
        )}
        {pending && (
          <>
            <div className="chat-msg user">
              <div className="chat-bubble">{pending}</div>
            </div>
            <div className="chat-msg agent pending">
              <span className="chat-dots" aria-hidden>
                <i />
                <i />
                <i />
              </span>
              <span className="small muted">{agent ? `Asking the ${agents.find((a) => a.name === agent)?.display_name ?? agent}…` : "Routing to the responsible agent…"}</span>
            </div>
          </>
        )}
        <div ref={endRef} />
      </div>

      {error && <div className="callout bad">{error}</div>}
      <form className="chat-form" onSubmit={submit}>
        <textarea
          className="input"
          rows={2}
          maxLength={2000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask about this repository — e.g. “Is the JWT handling safe?”"
          aria-label="Your question"
        />
        <div className="row chat-controls">
          <select className="input" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Who answers">
            <option value="">Route automatically</option>
            {agents.map((a) => (
              <option key={a.name} value={a.name}>
                {a.display_name}
              </option>
            ))}
          </select>
          <button className="btn primary" type="submit" disabled={!question.trim() || Boolean(pending)}>
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}
