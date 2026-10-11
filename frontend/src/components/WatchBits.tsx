import type { ImpactLevel, UpstreamChange } from "../types/account";

const IMPACT_TONE: Record<ImpactLevel, string> = { breaking: "imp-breaking", high: "imp-high", medium: "imp-medium", low: "imp-low", none: "imp-none" };

export function ImpactBadge({ level }: { level: ImpactLevel }) {
  return (
    <span className={`tag impact ${IMPACT_TONE[level]}`} title={`Impact on your code: ${level}`}>
      {level === "none" ? "no impact" : level}
    </span>
  );
}

const CHANGE_LABEL: Record<string, string> = {
  removed: "removed",
  moved: "moved",
  module_removed: "module removed",
  signature: "signature",
  deprecated: "deprecated",
  behavior: "behaviour",
  added: "added",
};

export function ChangeBadge({ change }: { change: Pick<UpstreamChange, "kind" | "severity"> }) {
  const tone = change.severity === "breaking" ? "bad" : change.severity === "deprecation" || change.severity === "behavior" ? "warn" : "neutral";
  return <span className={`tag ${tone}`}>{CHANGE_LABEL[change.kind] ?? change.kind}</span>;
}

/** Render `code` spans in the analysers' markdown-ish text. */
export function Ticks({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("`") && p.endsWith("`") && p.length > 1 ? (
          <code key={i} className="chip">
            {p.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}
