import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import type { ExecutionEvent, InvestigationBundle } from "../types/api";

const TERMINAL = new Set(["completed", "completed_with_limitations", "failed", "cancelled"]);

/** Polls every resource of an investigation while it runs; events are fetched incrementally. */
export function useInvestigation(id: string | undefined, intervalMs = 1200) {
  const [data, setData] = useState<InvestigationBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = useRef<ExecutionEvent[]>([]);
  const lastSeq = useRef(0);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    if (!id) return true;
    try {
      const [detail, agents, findings, evidence, correlations, verifications, risks, recommendations, actions, requests, newEvents] = await Promise.all([
        api.detail(id),
        api.agents(id),
        api.findings(id),
        api.evidence(id),
        api.correlations(id),
        api.verifications(id),
        api.risks(id),
        api.recommendations(id),
        api.actions(id),
        api.requests(id),
        api.events(id, lastSeq.current),
      ]);
      // Append only unseen events (guards against overlapping polls, e.g. StrictMode double effects).
      const fresh = newEvents.filter((e) => e.seq > lastSeq.current);
      if (fresh.length) {
        events.current = [...events.current, ...fresh];
        lastSeq.current = fresh[fresh.length - 1].seq;
      }
      setData({ detail, agents, findings, evidence, correlations, verifications, risks, recommendations, actions, requests, events: events.current });
      setError(null);
      return TERMINAL.has(detail.status);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, [id]);

  useEffect(() => {
    events.current = [];
    lastSeq.current = 0;
    let cancelled = false;
    const tick = async () => {
      const done = await load();
      if (!cancelled && !done) timer.current = window.setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [id, intervalMs, load]);

  return { data, error, refresh: load };
}
