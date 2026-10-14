import { useAuth } from "../auth/context";
import type { Health } from "../types/api";

/** The dry-run default for this person: their own preference, else the server's DRY_RUN. */
export function useDryRunDefault(health: Health | null): boolean {
  const { user } = useAuth();
  const pref = user?.preferences?.dry_run;
  return typeof pref === "boolean" ? pref : (health?.dry_run ?? true);
}

/** Changing code execution is deliberate: it is asked twice. Returns true when both are accepted. */
export function confirmExecChange(on: boolean): boolean {
  const what = on
    ? "Turn code execution ON? Skopeo will RUN this repository's own tests and scripts on the server."
    : "Turn code execution OFF? Skopeo will only read the code and will not run its tests or benchmarks.";
  if (!window.confirm(`${what}\n\nConfirmation 1 of 2`)) return false;
  return window.confirm(`Are you sure? ${on ? "Untrusted code will execute." : "Findings will not be confirmed by running tests."}\n\nConfirmation 2 of 2`);
}
