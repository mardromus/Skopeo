// Priority bands mirror backend/app/services/risk_scoring.py (P4 <12 <= P3 <35 <= P2 <60 <= P1 <80 <= P0).
const BANDS = [
  { p: "P4", from: 0, to: 12, c: "var(--info)" },
  { p: "P3", from: 12, to: 35, c: "var(--low)" },
  { p: "P2", from: 35, to: 60, c: "var(--med)" },
  { p: "P1", from: 60, to: 80, c: "var(--high)" },
  { p: "P0", from: 80, to: 100, c: "var(--crit)" },
];

/** Overall risk as a number on the real priority scale the risk agent uses. */
export function RiskScale({ score, level }: { score: number | null; level: string | null }) {
  const v = score ?? 0;
  return (
    <div className="scale" role="img" aria-label={`Overall risk ${score ?? "pending"} of 100, ${level ?? "pending"}`}>
      <span className="eyebrow">Overall risk</span>
      <div className="scale-score">
        <b>{score === null ? "··" : Math.round(v)}</b>
        <span className="of">/ 100 · {level ? level.toUpperCase() : "PENDING"}</span>
      </div>
      <div className="scale-track">
        {BANDS.map((b) => (
          <span key={b.p} className={score !== null && v >= b.from ? "hit" : ""} style={{ ["--c" as string]: b.c }} />
        ))}
        {score !== null && <div className="scale-marker" style={{ left: `${v}%` }} />}
      </div>
      <div className="scale-legend">
        {BANDS.map((b) => (
          <span key={b.p}>
            {b.p} {b.from}
          </span>
        ))}
      </div>
    </div>
  );
}
