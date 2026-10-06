import { useMemo, useState } from "react";
import { FindingCard } from "../../components/FindingCard";
import { SEVERITIES, agentName } from "../../lib/format";
import type { InvestigationBundle, Verification } from "../../types/api";

export function FindingsTab({ data }: { data: InvestigationBundle }) {
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [agent, setAgent] = useState("all");
  const [minConf, setMinConf] = useState(0);
  const [file, setFile] = useState("");

  const evidenceBy = useMemo(() => {
    const m: Record<string, typeof data.evidence> = {};
    for (const e of data.evidence) if (e.finding_id) (m[e.finding_id] ??= []).push(e);
    return m;
  }, [data]);
  const latestV = useMemo(() => {
    const m: Record<string, Verification> = {};
    for (const v of data.verifications) if (v.finding_id) m[v.finding_id] = v;
    return m;
  }, [data]);
  const categories = Array.from(new Set(data.findings.map((f) => f.category))).sort();
  const agents = Array.from(new Set(data.findings.map((f) => f.agent))).sort();
  const rank = (s: string) => SEVERITIES.indexOf(s as (typeof SEVERITIES)[number]);
  const shown = data.findings
    .filter((f) => severity === "all" || f.severity === severity)
    .filter((f) => category === "all" || f.category === category)
    .filter((f) => status === "all" || f.status === status)
    .filter((f) => agent === "all" || f.agent === agent)
    .filter((f) => f.confidence >= minConf / 100)
    .filter((f) => !file || f.affected_files.some((p) => p.toLowerCase().includes(file.toLowerCase())))
    .sort((a, b) => rank(a.severity) - rank(b.severity) || b.confidence - a.confidence);

  return (
    <div>
      <div className="filters">
        <select id="f-sev" className="input" value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
          <option value="all">Any severity</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select id="f-cat" className="input" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="all">Any category</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
        <select id="f-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Ruling">
          <option value="all">Any ruling</option>
          <option value="verified">verified</option>
          <option value="rejected">rejected</option>
          <option value="needs_more_evidence">insufficient evidence</option>
          <option value="correlated">not yet ruled (correlated)</option>
          <option value="proposed">not yet ruled (proposed)</option>
        </select>
        <select id="f-agent" className="input" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
          <option value="all">Any agent</option>
          {agents.map((a) => (
            <option key={a} value={a}>
              {agentName(a)}
            </option>
          ))}
        </select>
        <label className="field" htmlFor="f-conf">
          Confidence at least {minConf}%
          <input id="f-conf" type="range" min={0} max={100} step={5} value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} />
        </label>
        <input id="f-file" className="input mono" placeholder="file path contains…" value={file} onChange={(e) => setFile(e.target.value)} aria-label="Affected file" />
      </div>
      <p className="small muted" style={{ margin: "0 0 10px" }}>
        {shown.length} of {data.findings.length} findings. Open one to read its evidence, how its confidence was computed, and the red team's ruling.
      </p>
      {shown.length === 0 ? (
        <p className="empty">No findings match these filters.</p>
      ) : (
        <div className="findings">
          {shown.map((f) => (
            <FindingCard key={f.finding_id} f={f} evidence={evidenceBy[f.finding_id] ?? []} verification={latestV[f.finding_id]} />
          ))}
        </div>
      )}
    </div>
  );
}
