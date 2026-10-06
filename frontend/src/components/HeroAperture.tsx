import { useState } from "react";
import { Link } from "react-router-dom";
import { BLADES, aperturePaths, openingRadius } from "../lib/aperture";
import { SPECIALISTS, caseNo, shortAgent } from "../lib/format";
import type { AgentCoverage, InvestigationDetail } from "../types/api";
import { AnimatedNumber } from "./AnimatedNumber";
import { Aperture } from "./Aperture";

const STATUS_FILL: Record<string, string> = {
  complete: "var(--signal)",
  partial: "color-mix(in oklab, var(--signal) 42%, var(--surface))",
  unavailable: "var(--bad)",
  skipped: "var(--line-2)",
};
const STATUS_TEXT: Record<string, string> = {
  complete: "full coverage",
  partial: "partial coverage",
  unavailable: "unavailable",
  skipped: "not run",
};

/**
 * The landing hero: one blade per specialist, coloured by that agent's real coverage in the most
 * recent case, with the case's overall risk in the opening. Hover a blade to read its note.
 */
export function HeroAperture({ detail }: { detail: InvestigationDetail | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const size = 300;
  const coverage = detail?.coverage?.agents ?? {};
  const fills = SPECIALISTS.map((a) => (coverage[a] ? STATUS_FILL[coverage[a].status] ?? "var(--line-2)" : undefined));
  const hasCase = fills.some(Boolean);
  // label angles follow the blade geometry at the resting opening
  const mids = aperturePaths(openingRadius(0.56)).map((b) => b.mid);
  const box = 460;
  const ring = size / 2 + 28;
  const active: AgentCoverage | undefined = hover !== null ? coverage[SPECIALISTS[hover]] : undefined;
  const score = detail?.overall_risk?.score;

  return (
    <figure className="hero-aperture" aria-label="Agent coverage in the latest case">
      <div className="hero-stage">
        <div className="hero-rings" aria-hidden />
        <div className="hero-mark">
          <Aperture
            size={size}
            openness={0.56}
            breathe
            ring
            focus={false}
            gap="var(--paper)"
            fills={hasCase ? fills.map((f) => f ?? "var(--line-2)") : undefined}
            highlight={hover}
            onBladeHover={setHover}
            title={hasCase ? "Coverage of the eight specialist agents in the latest case" : "Skopeo aperture: eight specialist agents"}
          />
          <div className="hero-core">
            {score != null ? (
              <>
                <b>
                  <AnimatedNumber value={score} />
                </b>
                <span>risk</span>
              </>
            ) : (
              <>
                <b>{BLADES}</b>
                <span>agents</span>
              </>
            )}
          </div>
        </div>
        {SPECIALISTS.map((a, i) => {
          const ang = mids[i];
          const x = box / 2 + Math.cos(ang) * ring;
          const y = box / 2 + Math.sin(ang) * ring;
          const right = Math.cos(ang) >= -0.05;
          const c = coverage[a];
          return (
            <button
              key={a}
              className={`hero-label ${hover === i ? "on" : ""}`}
              style={{ left: x, top: y, transform: `translate(${right ? "0" : "-100%"}, -50%)`, textAlign: right ? "left" : "right" }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <span className="hl-name">{shortAgent(a)}</span>
              {c && <span className="hl-meta">{c.findings ?? 0} findings</span>}
            </button>
          );
        })}
      </div>
      <figcaption className="hero-caption">
        {hover !== null ? (
          <>
            <b>{shortAgent(SPECIALISTS[hover])}</b>
            {active ? (
              <>
                {" "}
                · {STATUS_TEXT[active.status] ?? active.status}. {(active.limitations ?? [])[0] ?? active.reason ?? "Examined everything in scope."}
              </>
            ) : (
              " · runs in every standard investigation."
            )}
          </>
        ) : hasCase && detail ? (
          <>
            Blades show each specialist&apos;s coverage in <Link to={`/investigations/${detail.investigation_id}`}>{caseNo(detail.investigation_id)}</Link>. Hover one to read it.
          </>
        ) : (
          <>Eight blades, one per specialist agent. Run a case to colour them with real coverage.</>
        )}
        {hasCase && (
          <span className="hero-legend">
            <i style={{ background: "var(--signal)" }} /> full
            <i style={{ background: "color-mix(in oklab, var(--signal) 42%, var(--surface))" }} /> partial
            <i style={{ background: "var(--bad)" }} /> unavailable
            <i style={{ background: "var(--line-2)" }} /> not run
          </span>
        )}
      </figcaption>
    </figure>
  );
}
