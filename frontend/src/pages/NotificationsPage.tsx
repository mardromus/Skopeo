import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { StatusBadge } from "../components/Badges";
import { useAuth } from "../auth/context";
import { fmtTime } from "../lib/format";
import { notificationsApi, projectsApi } from "../services/api";
import type { Channel, ChannelKind, Delivery, NotificationCatalog, Project, Rule } from "../types/account";

const KIND_LABEL: Record<ChannelKind, string> = { email: "Email", slack: "Slack", discord: "Discord", webhook: "Webhook" };
const PLACEHOLDER: Record<ChannelKind, string> = {
  email: "you@company.com",
  slack: "https://hooks.slack.com/services/T000/B000/XXXX",
  discord: "https://discord.com/api/webhooks/123/abc",
  webhook: "https://ci.example.com/hooks/skopeo",
};
const HELP: Record<ChannelKind, string> = {
  email: "Addresses other than your sign-in address get a 6-digit confirmation code first.",
  slack: "In Slack: Apps > Incoming Webhooks > Add to a channel, then paste the webhook URL.",
  discord: "In Discord: Channel settings > Integrations > Webhooks > New webhook > Copy URL.",
  webhook: "Skopeo POSTs JSON with an X-Skopeo-Signature HMAC header you can verify with the signing secret.",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function NotificationsPage() {
  const { user } = useAuth();
  const [catalog, setCatalog] = useState<NotificationCatalog | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [c, ch, r, d, p] = await Promise.all([
        notificationsApi.catalog(),
        notificationsApi.channels(),
        notificationsApi.rules(),
        notificationsApi.deliveries(),
        projectsApi.list(),
      ]);
      setCatalog(c);
      setChannels(ch);
      setRules(r);
      setDeliveries(d);
      setProjects(p);
    } catch (err) {
      setError(errText(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (!catalog) return <main className="page">{error ? <div className="callout bad">{error}</div> : <p className="muted">Loading…</p>}</main>;

  return (
    <main className="page narrow">
      <span className="eyebrow">Settings</span>
      <h1 className="page-title">Notifications</h1>
      <p className="lede ink2">
        Connect the places where you want to hear from Skopeo, then choose what each one receives: finished cases, high-priority risks, or upstream changes that affect your projects.
      </p>
      {catalog.dry_run && <div className="callout warn">This server runs with NOTIFICATIONS_DRY_RUN on: deliveries are logged but nothing is sent.</div>}
      {error && <div className="callout bad">{error}</div>}

      <section className="section">
        <div className="section-head">
          <h2>Channels</h2>
          <span className="note">{channels.length ? `${channels.length} connected` : "None yet"}</span>
        </div>
        <div className="stack">
          {channels.map((c) => (
            <ChannelCard key={c.channel_id} channel={c} catalog={catalog} onChange={reload} />
          ))}
        </div>
        <AddChannel catalog={catalog} userEmail={user?.provider === "local" ? null : (user?.email ?? null)} onAdded={reload} />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Rules</h2>
          <span className="note">Fine-tune when each event is sent</span>
        </div>
        <RulesEditor catalog={catalog} rules={rules} channels={channels} projects={projects} onChange={reload} />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Delivery log</h2>
          <button className="btn sm quiet" onClick={() => void reload()}>
            Refresh
          </button>
        </div>
        {deliveries.length === 0 ? (
          <p className="empty">Nothing sent yet. Use “Send test” on a channel to try it.</p>
        ) : (
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Event</th>
                  <th>Channel</th>
                  <th>Subject</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {deliveries.map((d) => (
                  <tr key={d.delivery_id}>
                    <td className="mono small">{fmtTime(d.created_at)}</td>
                    <td className="mono small">{d.event}</td>
                    <td className="small">{channels.find((c) => c.channel_id === d.channel_id)?.name ?? "—"}</td>
                    <td className="small">{d.subject}</td>
                    <td>
                      <DeliveryBadge status={d.status} />
                      {d.error && <div className="small muted">{d.error}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function DeliveryBadge({ status }: { status: Delivery["status"] }) {
  const map = { sent: "completed", failed: "failed", skipped: "skipped", dry_run: "waiting" } as const;
  const label = { sent: "Sent", failed: "Failed", skipped: "Skipped", dry_run: "Dry run" }[status];
  return <StatusBadge status={map[status]} label={label} />;
}

function EventChecks({ catalog, value, onChange }: { catalog: NotificationCatalog; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="event-checks">
      {catalog.events.map((e) => (
        <label key={e.event} className="check-label" title={e.description}>
          <input
            type="checkbox"
            checked={value.includes(e.event)}
            onChange={(ev) => onChange(ev.target.checked ? [...value, e.event] : value.filter((x) => x !== e.event))}
          />
          {e.label}
        </label>
      ))}
    </div>
  );
}

function AddChannel({ catalog, userEmail, onAdded }: { catalog: NotificationCatalog; userEmail: string | null; onAdded: () => Promise<void> }) {
  const [kind, setKind] = useState<ChannelKind>("email");
  const [name, setName] = useState("");
  const [target, setTarget] = useState(userEmail ?? "");
  const [events, setEvents] = useState<string[]>(catalog.default_subscriptions);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await notificationsApi.createChannel({ kind, name, target: target.trim(), events });
      if (res.signing_secret) setSecret(res.signing_secret);
      if (!res.channel.verified) {
        setNotice(
          res.verification_sent
            ? `We sent a 6-digit code to ${res.channel.target}. Enter it on the channel below.${res.dev_verification_code ? ` (dry run code: ${res.dev_verification_code})` : ""}`
            : `The confirmation email could not be sent: ${res.verification_error ?? "email is not configured on this server"}.`,
        );
      }
      setName("");
      setTarget("");
      await onAdded();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h3>Add a channel</h3>
      <div className="seg" role="radiogroup" aria-label="Channel type">
        {catalog.channel_kinds.map((k) => (
          <button
            type="button"
            key={k.kind}
            role="radio"
            aria-checked={kind === k.kind}
            className={`seg-btn ${kind === k.kind ? "on" : ""}`}
            onClick={() => {
              setKind(k.kind);
              setTarget(k.kind === "email" ? (userEmail ?? "") : "");
            }}
          >
            {KIND_LABEL[k.kind]}
          </button>
        ))}
      </div>
      {kind === "email" && !catalog.email_configured && (
        <div className="callout warn">Email sending is not configured on this server yet (SMTP_HOST). You can add the address now; messages are logged as failed until SMTP is set up.</div>
      )}
      <div className="form-row">
        <label className="field">
          {kind === "email" ? "Email address" : "Webhook URL"}
          <input className="input mono" value={target} onChange={(e) => setTarget(e.target.value)} placeholder={PLACEHOLDER[kind]} required autoComplete="off" />
        </label>
        <label className="field">
          Name (optional)
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={kind === "email" ? "Work inbox" : "#dependency-alerts"} maxLength={120} />
        </label>
      </div>
      <span className="small muted">{HELP[kind]}</span>
      <div className="field">
        Send me
        <EventChecks catalog={catalog} value={events} onChange={setEvents} />
      </div>
      {error && <div className="callout bad">{error}</div>}
      {notice && <div className="callout ok">{notice}</div>}
      {secret && (
        <div className="callout warn">
          Signing secret (shown once, store it with your webhook receiver): <code className="chip">{secret}</code>
        </div>
      )}
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy || !target.trim()}>
          Connect {KIND_LABEL[kind]}
        </button>
      </div>
    </form>
  );
}

function ChannelCard({ channel, catalog, onChange }: { channel: Channel; catalog: NotificationCatalog; onChange: () => Promise<void> }) {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [events, setEvents] = useState(channel.events);

  const act = async (fn: () => Promise<string | void>) => {
    setBusy(true);
    setMsg(null);
    try {
      const text = await fn();
      if (text) setMsg({ tone: "ok", text });
      await onChange();
    } catch (err) {
      setMsg({ tone: "bad", text: errText(err) });
    } finally {
      setBusy(false);
    }
  };

  const eventLabels = channel.events.map((e) => catalog.events.find((x) => x.event === e)?.label ?? e);
  return (
    <div className={`channel ${channel.enabled ? "" : "off"}`}>
      <div className="channel-head">
        <span className={`kind-badge k-${channel.kind}`}>{KIND_LABEL[channel.kind]}</span>
        <div className="minw0">
          <b>{channel.name}</b>
          <div className="small mono muted wrap-any">{channel.target}</div>
        </div>
        <span className="spacer" />
        {!channel.verified ? <StatusBadge status="needs_more_evidence" label="Unconfirmed" /> : channel.enabled ? <StatusBadge status="completed" label="Active" /> : <StatusBadge status="cancelled" label="Paused" />}
      </div>
      {!channel.verified && (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              await notificationsApi.verify(channel.channel_id, code);
              return "Confirmed. This address will now receive notifications.";
            });
          }}
        >
          <input className="input mono code-input" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} placeholder="6-digit code" maxLength={12} />
          <button className="btn sm primary" disabled={busy || code.trim().length < 4}>
            Confirm
          </button>
          <button
            type="button"
            className="btn sm quiet"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const r = await notificationsApi.resend(channel.channel_id);
                return r.verification_sent ? `New code sent.${r.dev_verification_code ? ` (dry run code: ${r.dev_verification_code})` : ""}` : `Could not send: ${r.verification_error}`;
              })
            }
          >
            Send a new code
          </button>
        </form>
      )}
      <div className="small ink2">
        {eventLabels.length ? (
          <>
            Receives: <span className="ink">{eventLabels.join(" · ")}</span>
          </>
        ) : (
          <span className="muted">Not subscribed to any event</span>
        )}
        {channel.last_used_at && <span className="muted"> · last sent {fmtTime(channel.last_used_at)}</span>}
      </div>
      {channel.last_error && <div className="small" style={{ color: "var(--bad)" }}>Last error: {channel.last_error}</div>}
      {editing && (
        <div className="stack">
          <EventChecks catalog={catalog} value={events} onChange={setEvents} />
          <div className="row">
            <button
              className="btn sm primary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await notificationsApi.updateChannel(channel.channel_id, { events });
                  setEditing(false);
                })
              }
            >
              Save events
            </button>
            <button className="btn sm quiet" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {msg && <div className={`callout ${msg.tone}`}>{msg.text}</div>}
      <div className="row">
        <button
          className="btn sm"
          disabled={busy || !channel.verified}
          onClick={() =>
            void act(async () => {
              const r = await notificationsApi.test(channel.channel_id);
              if (r.status === "failed") throw new Error(r.error ?? "delivery failed");
              return r.status === "dry_run" ? "Logged (dry run): nothing was sent." : "Test message sent.";
            })
          }
        >
          Send test
        </button>
        {!editing && (
          <button className="btn sm" onClick={() => setEditing(true)}>
            Choose events
          </button>
        )}
        <button className="btn sm" disabled={busy} onClick={() => void act(async () => void (await notificationsApi.updateChannel(channel.channel_id, { enabled: !channel.enabled })))}>
          {channel.enabled ? "Pause" : "Resume"}
        </button>
        {channel.kind === "webhook" && (
          <button
            className="btn sm"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const r = await notificationsApi.rotateSecret(channel.channel_id);
                return `New signing secret (shown once): ${r.signing_secret}`;
              })
            }
          >
            Rotate secret
          </button>
        )}
        <span className="spacer" />
        <button
          className="btn sm danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Remove the channel “${channel.name}”?`)) void act(async () => void (await notificationsApi.deleteChannel(channel.channel_id)));
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function RulesEditor({
  catalog,
  rules,
  channels,
  projects,
  onChange,
}: {
  catalog: NotificationCatalog;
  rules: Rule[];
  channels: Channel[];
  projects: Project[];
  onChange: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const byEvent = useMemo(() => {
    const m: Record<string, Rule[]> = {};
    for (const r of rules) (m[r.event] ??= []).push(r);
    return m;
  }, [rules]);

  const save = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await onChange();
    } catch (err) {
      setError(errText(err));
    }
  };

  if (!channels.length) return <p className="empty">Add a channel first; rules decide which events reach which channels.</p>;
  return (
    <div className="rules">
      {error && <div className="callout bad">{error}</div>}
      {catalog.events.map((e) => {
        const list = byEvent[e.event] ?? [];
        return (
          <div key={e.event} className="rule-group">
            <div className="rule-event">
              <b>{e.label}</b>
              <span className="small muted">{e.description}</span>
            </div>
            <div className="stack">
              {list.length === 0 && <span className="small muted">Off. Turn it on for a channel above, or add a rule.</span>}
              {list.map((r) => (
                <RuleRow key={r.rule_id} rule={r} event={e.event} filters={e.filters} catalog={catalog} channels={channels} projects={projects} save={save} />
              ))}
              <div>
                <button
                  className="btn sm quiet"
                  onClick={() => void save(() => notificationsApi.createRule({ event: e.event, channel_ids: [channels[0].channel_id], filters: {} }))}
                >
                  + Add a rule
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RuleRow({
  rule,
  event,
  filters,
  catalog,
  channels,
  projects,
  save,
}: {
  rule: Rule;
  event: string;
  filters: string[];
  catalog: NotificationCatalog;
  channels: Channel[];
  projects: Project[];
  save: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const setFilter = (key: string, value: string) => {
    const next = { ...rule.filters };
    if (value) next[key] = value;
    else delete next[key];
    void save(() => notificationsApi.updateRule(rule.rule_id, { filters: next }));
  };
  const watches = projects.flatMap((p) => p.watches.map((w) => ({ ...w, projectName: p.name })));
  return (
    <div className={`rule-row ${rule.enabled ? "" : "off"}`} data-event={event}>
      <label className="check-label">
        <input type="checkbox" checked={rule.enabled} onChange={(e) => void save(() => notificationsApi.updateRule(rule.rule_id, { enabled: e.target.checked }))} />
        On
      </label>
      <div className="chan-picks">
        {channels.map((c) => (
          <label key={c.channel_id} className="check-label">
            <input
              type="checkbox"
              checked={rule.channel_ids.includes(c.channel_id)}
              onChange={(e) =>
                void save(() =>
                  notificationsApi.updateRule(rule.rule_id, {
                    channel_ids: e.target.checked ? [...rule.channel_ids, c.channel_id] : rule.channel_ids.filter((x) => x !== c.channel_id),
                  }),
                )
              }
            />
            {c.name}
          </label>
        ))}
      </div>
      {filters.includes("min_priority") && (
        <label className="field inline">
          at or above
          <select className="input" value={rule.filters.min_priority ?? ""} onChange={(e) => setFilter("min_priority", e.target.value)}>
            <option value="">any priority</option>
            {catalog.priorities.slice(0, 4).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      )}
      {filters.includes("min_impact") && (
        <label className="field inline">
          impact at least
          <select className="input" value={rule.filters.min_impact ?? ""} onChange={(e) => setFilter("min_impact", e.target.value)}>
            <option value="">any</option>
            {catalog.impact_levels.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      )}
      {filters.includes("project_id") && projects.length > 0 && (
        <label className="field inline">
          project
          <select className="input" value={rule.filters.project_id ?? ""} onChange={(e) => setFilter("project_id", e.target.value)}>
            <option value="">all projects</option>
            {projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {filters.includes("watch_id") && watches.length > 0 && (
        <label className="field inline">
          repository
          <select className="input" value={rule.filters.watch_id ?? ""} onChange={(e) => setFilter("watch_id", e.target.value)}>
            <option value="">all watched repositories</option>
            {watches.map((w) => (
              <option key={w.watch_id} value={w.watch_id}>
                {w.upstream_name} ({w.projectName})
              </option>
            ))}
          </select>
        </label>
      )}
      <button className="btn sm quiet danger" onClick={() => void save(() => notificationsApi.deleteRule(rule.rule_id))} aria-label="Delete rule">
        Delete
      </button>
    </div>
  );
}
