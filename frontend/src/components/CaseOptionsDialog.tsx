import { useEffect, useRef, useState } from "react";
import { confirmExecChange, useDryRunDefault } from "../lib/caseOptions";
import { api } from "../services/api";
import type { Health } from "../types/api";

export interface CaseOptions {
  enable_github_actions: boolean;
  dry_run: boolean;
  sandbox_execution: boolean;
}

/**
 * Pop-up shown before any case starts (home page, GitHub import, anywhere): choose whether
 * approved actions may reach GitHub, dry run, and code execution for this one case.
 */
export function CaseOptionsDialog({
  open,
  repo,
  onStart,
  onClose,
  busy = false,
  error = null,
}: {
  open: boolean;
  repo: string;
  onStart: (o: CaseOptions) => void;
  onClose: () => void;
  busy?: boolean;
  error?: string | null;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const dryDefault = useDryRunDefault(health);
  const [actions, setActions] = useState(false);
  const [dry, setDry] = useState<boolean | null>(null);
  const [exec, setExec] = useState<boolean | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setDry(null);
      setExec(null);
      setActions(false);
      api
        .health()
        .then(setHealth)
        .catch(() => setHealth(null));
      d.showModal();
    } else if (!open && d.open) d.close();
  }, [open]);

  const serverExec = Boolean(health?.sandbox_execution);
  const canExec = serverExec || Boolean(health?.allow_case_execution);
  const dryRun = dry ?? dryDefault;
  const execOn = exec ?? serverExec;

  return (
    <dialog ref={ref} className="modal" onClose={onClose} onCancel={onClose} aria-labelledby="case-opts-title">
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onStart({
            enable_github_actions: actions,
            dry_run: dryRun,
            sandbox_execution: execOn,
          });
        }}
      >
        <h2 id="case-opts-title">Start a case</h2>
        <p className="small muted mono">{repo}</p>

        <fieldset className="opt">
          <legend>Dry run</legend>
          <label className="check-label">
            <input type="radio" name="dry" checked={dryRun} onChange={() => setDry(true)} />
            <span>
              <b>On</b>: approving an action only records it. Nothing is sent to GitHub.
            </span>
          </label>
          <label className="check-label">
            <input type="radio" name="dry" checked={!dryRun} onChange={() => setDry(false)} />
            <span>
              <b>Off</b>: approving an action creates the real issue or draft PR on GitHub.
            </span>
          </label>
          <span className="small muted">You can switch this later on the case page, even while it runs.</span>
        </fieldset>

        <label className="check-label">
          <input type="checkbox" checked={actions} onChange={(e) => setActions(e.target.checked)} />
          Let approved issues and draft PRs be sent to GitHub for this case
        </label>

        <fieldset className="opt">
          <legend>Code execution</legend>
          <label className="check-label">
            <input type="radio" name="exec" checked={!execOn} onChange={() => !execOn || (confirmExecChange(false) && setExec(false))} />
            <span>
              <b>Off</b>: read the code only, never run it.
            </span>
          </label>
          <label className="check-label">
            <input type="radio" name="exec" checked={execOn} disabled={!canExec} onChange={() => execOn || (confirmExecChange(true) && setExec(true))} />
            <span>
              <b>On</b>: run the repository's tests in the sandbox
              {canExec ? "" : " (not allowed on this server)"}.
            </span>
          </label>
          <span className="small muted">Changing this asks you to confirm twice.</span>
        </fieldset>

        {error && <div className="callout bad">{error}</div>}
        <div className="row modal-actions">
          <button type="button" className="btn quiet" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? "Starting…" : "Start investigation"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

/** On a case page: shows this case's dry run and switches it at any time, also while the case runs. */
export function CaseDryRunSwitch({ caseId, value, onChange }: { caseId: string; value: boolean | null | undefined; onChange: () => void }) {
  const [serverDefault, setServerDefault] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (typeof value !== "boolean")
      api
        .health()
        .then((h) => setServerDefault(h.dry_run))
        .catch(() => setServerDefault(true));
  }, [value]);
  const on = typeof value === "boolean" ? value : (serverDefault ?? true);
  return (
    <span className="dry-switch">
      <span className={`tag ${on ? "ok" : "warn"}`} title={on ? "Approvals are recorded only; nothing is sent to GitHub" : "Approving an action sends it to GitHub"}>
        dry run {on ? "on" : "off"}
      </span>
      <button
        type="button"
        className="btn sm quiet"
        disabled={busy}
        onClick={async () => {
          const msg = on
            ? "Turn dry run OFF for this case? From now on, approving an action creates the real issue or draft PR on GitHub."
            : "Turn dry run ON for this case? From now on, approvals are only recorded.";
          if (!window.confirm(msg)) return;
          setBusy(true);
          setError(null);
          try {
            await api.setCaseOptions(caseId, { dry_run: !on });
            onChange();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {on ? "Turn dry run off" : "Turn dry run on"}
      </button>
      {error && (
        <span className="small" style={{ color: "var(--bad)" }}>
          {error}
        </span>
      )}
    </span>
  );
}
