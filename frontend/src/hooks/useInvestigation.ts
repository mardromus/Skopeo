import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import type { ExecutionEvent, InvestigationBundle } from "../types/api";

const TERMINAL = new Set(["completed", "completed_with_limitations", "failed", "cancelled"]);
const FULL_REFRESH_MS = 10_000;

/**
 * Live view of one investigation.
 *
 * Every tick fetches only the events after the last one seen (cheap). The full bundle — findings,
 * evidence, rulings, risks … — is refetched only when new events arrived (something changed),
 * on the first load, and every 10 s as a safety net. Polling stops once the case is finished.
 */
export function useInvestigation(id: string | undefined, intervalMs = 1200) {
  const [data, setData] = useState<InvestigationBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = useRef<ExecutionEvent[]>([]);
  const lastSeq = useRef(0);
  const lastFull = useRef(0);

  const loadAll = useCallback(async () => {
    if (!id) return true;
    const [detail, agents, findings, evidence, correlations, verifications, risks, recommendations, actions, requests] = await Promise.all([
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
    ]);
    lastFull.current = Date.now();
    setData({ detail, agents, findings, evidence, correlations, verifications, risks, recommendations, actions, requests, events: events.current });
    return TERMINAL.has(detail.status);
  }, [id]);

  const pollEvents = useCallback(async () => {
    if (!id) return 0;
    const fresh = (await api.events(id, lastSeq.current)).filter((e) => e.seq > lastSeq.current);
    if (fresh.length) {
      events.current = [...events.current, ...fresh];
      lastSeq.current = fresh[fresh.length - 1].seq;
    }
    return fresh.length;
  }, [id]);

  const refresh = useCallback(async () => {
    try {
      await pollEvents();
      return await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, [loadAll, pollEvents]);

  useEffect(() => {
    events.current = [];
    lastSeq.current = 0;
    lastFull.current = 0;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      let done = false;
      try {
        const fresh = await pollEvents();
        if (fresh > 0 || lastFull.current === 0 || Date.now() - lastFull.current > FULL_REFRESH_MS) {
          done = await loadAll();
        } else {
          setData((d) => (d && d.events !== events.current ? { ...d, events: events.current } : d));
        }
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
      if (!cancelled && !done) timer = window.setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [id, intervalMs, loadAll, pollEvents]);

  return { data, error, refresh };
}
