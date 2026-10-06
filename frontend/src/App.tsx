import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { InvestigationPage } from "./pages/InvestigationPage";
import { api } from "./services/api";
import type { Health } from "./types/api";

type Theme = "system" | "light" | "dark";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem("skopeo-theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  if (t === "system") delete root.dataset.theme;
  else root.dataset.theme = t;
  try {
    if (t === "system") localStorage.removeItem("skopeo-theme");
    else localStorage.setItem("skopeo-theme", t);
  } catch {
    /* storage unavailable: the choice lasts for this page view */
  }
}

function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="6" fill="var(--signal)" />
      <circle cx="14" cy="14" r="7" fill="none" stroke="var(--signal-ink)" strokeWidth="3" />
      <path d="M19 19l7 7" stroke="var(--signal-ink)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  const nextTheme = () => {
    const order: Theme[] = ["system", "light", "dark"];
    const t = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(t);
    applyTheme(t);
  };

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="wordmark">
          <Mark />
          <b>Skopeo</b>
          <span>Repository intelligence and risk analysis</span>
        </Link>
        <span className="spacer" />
        <div className="env" aria-label="Server configuration">
          {healthError && <span style={{ color: "var(--bad)" }}>API unreachable on /api</span>}
          {health && (
            <>
              <span title="Which model makes the agents' decisions">llm: {health.llm_provider}</span>
              <span className={health.dry_run ? "on" : "warnc"} title="With dry run on, approved GitHub actions are recorded but never sent">
                dry run: {health.dry_run ? "on" : "off"}
              </span>
              <span title="Whether tests and benchmarks of cloned repositories may run">repo code exec: {health.sandbox_execution ? "sandbox" : "off"}</span>
              <span>v{health.version}</span>
            </>
          )}
          <button className="theme-toggle" onClick={nextTheme} title="Switch colour theme">
            theme: {theme}
          </button>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<HomePage health={health} />} />
        <Route path="/investigations/:id" element={<InvestigationPage />} />
      </Routes>
    </div>
  );
}
