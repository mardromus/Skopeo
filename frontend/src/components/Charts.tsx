import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SEVERITIES } from "../lib/format";
import type { Finding, Risk } from "../types/api";

type TooltipPayload = { payload: Record<string, unknown> }[];
const AXIS = { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--mono)" };

function SevTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as { label: string; total: number; verified: number; rejected: number; insufficient: number };
  return (
    <div className="tt">
      <b>{p.label}</b> · {p.total} finding(s)
      <div className="muted">
        {p.verified} verified, {p.rejected} rejected, {p.insufficient} insufficient evidence
      </div>
    </div>
  );
}

/** Findings per severity — one series; severity identity is carried by the axis labels. */
export function SeverityChart({ findings }: { findings: Finding[] }) {
  const data = SEVERITIES.map((s) => {
    const fs = findings.filter((f) => f.severity === s);
    return {
      label: s[0].toUpperCase() + s.slice(1),
      total: fs.length,
      verified: fs.filter((f) => f.status === "verified").length,
      rejected: fs.filter((f) => f.status === "rejected").length,
      insufficient: fs.filter((f) => f.status === "needs_more_evidence").length,
    };
  });
  return (
    <div style={{ width: "100%", height: 180 }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 34, left: 0, bottom: 2 }}>
          <CartesianGrid horizontal={false} stroke="var(--line)" />
          <XAxis type="number" allowDecimals={false} tick={AXIS} axisLine={{ stroke: "var(--line-2)" }} tickLine={false} />
          <YAxis type="category" dataKey="label" width={64} tick={{ fill: "var(--ink-2)", fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip content={<SevTooltip />} cursor={{ fill: "var(--sunken)" }} />
          <Bar dataKey="total" fill="var(--signal)" barSize={14} radius={[0, 3, 3, 0]} isAnimationActive={false}>
            <LabelList dataKey="total" position="right" style={{ fill: "var(--ink-2)", fontSize: 12, fontFamily: "var(--mono)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RiskTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload as unknown as Risk;
  return (
    <div className="tt">
      <b>
        {r.priority} · {r.score}
      </b>
      <div style={{ margin: "3px 0" }}>{r.title}</div>
      <div className="muted mono">
        conf {r.confidence.toFixed(2)} · impact {r.impact.toFixed(2)} · expl {r.exploitability.toFixed(2)} · ×{r.correlation_multiplier}
      </div>
    </div>
  );
}

/** Verified risks ranked by score, with the P1/P0 thresholds drawn as reference lines. */
export function RiskScoreChart({ risks }: { risks: Risk[] }) {
  const data = risks.slice(0, 10).map((r, i) => ({ ...r, label: `#${i + 1} ${r.priority}` }));
  return (
    <div style={{ width: "100%", height: Math.max(140, data.length * 26 + 30) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 38, left: 0, bottom: 2 }}>
          <CartesianGrid horizontal={false} stroke="var(--line)" />
          <XAxis type="number" domain={[0, 100]} ticks={[0, 12, 35, 60, 80, 100]} tick={AXIS} axisLine={{ stroke: "var(--line-2)" }} tickLine={false} />
          <YAxis type="category" dataKey="label" width={62} tick={{ fill: "var(--ink-2)", fontSize: 11.5, fontFamily: "var(--mono)" }} axisLine={false} tickLine={false} />
          <Tooltip content={<RiskTooltip />} cursor={{ fill: "var(--sunken)" }} />
          <Bar dataKey="score" fill="var(--signal)" barSize={12} radius={[0, 3, 3, 0]} isAnimationActive={false}>
            <LabelList dataKey="score" position="right" style={{ fill: "var(--ink-2)", fontSize: 11.5, fontFamily: "var(--mono)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
