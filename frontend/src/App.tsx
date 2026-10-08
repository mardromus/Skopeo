import { Suspense, lazy, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Aperture } from "./components/Aperture";
import { Logo } from "./components/Logo";
import { HomePage } from "./pages/HomePage";

// The case view (charts, trace, rulings) loads on demand, keeping the landing page light.
const InvestigationPage = lazy(() => import("./pages/InvestigationPage").then((m) => ({ default: m.InvestigationPage })));
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

/** True while any investigation on the server is queued or running. */
function useAnyLive(): boolean {
  const [live, setLive] = useState(false);
  const location = useLocation();
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .list()
        .then((list) => alive && setLive(list.some((i) => i.status === "running" || i.status === "queued")))
        .catch(() => alive && setLive(false));
    check();
    const t = window.setInterval(check, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [location.pathname]);
  return live;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [theme, setTheme] = useState<Theme>(readTheme);
  const live = useAnyLive();

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
        <Link to="/" className="wordmark" aria-label="Skopeo home">
          <Logo live={live} />
        </Link>
        <nav className="mainnav" aria-label="Main">
          <NavLink to="/" end>
            Cases
          </NavLink>
          <a href="/docs" target="_blank" rel="noreferrer">
            API
          </a>
        </nav>
        <span className="spacer" />
        <div className="env" aria-label="Server configuration">
          {live && (
            <span className="live-pill">
              <i aria-hidden /> agents working
            </span>
          )}
          {healthError && <span style={{ color: "var(--bad)" }}>API unreachable on /api</span>}
          {health && (
            <>
              <span title="Which model makes the agents' decisions">llm {health.llm_provider}</span>
              <span className={health.dry_run ? "on" : "warnc"} title="With dry run on, approved GitHub actions are recorded but never sent">
                dry run {health.dry_run ? "on" : "off"}
              </span>
              <span className="hide-sm" title="Whether tests and benchmarks of cloned repositories may run">
                repo exec {health.sandbox_execution ? "sandbox" : "off"}
              </span>
            </>
          )}
          <button className="theme-toggle" onClick={nextTheme} title="Switch colour theme">
            {theme === "system" ? "◐ auto" : theme === "light" ? "○ light" : "● dark"}
          </button>
        </div>
        {live && <span className="live-bar" aria-hidden />}
      </header>
      <div className="app-body">
        <Routes>
          <Route path="/" element={<HomePage health={health} />} />
          <Route
            path="/investigations/:id"
            element={
              <Suspense
                fallback={
                  <main className="page loading">
                    <Aperture size={96} live gap="var(--paper)" title="Loading" />
                    <span className="muted">Opening case…</span>
                  </main>
                }
              >
                <InvestigationPage />
              </Suspense>
            }
          />
        </Routes>
      </div>
      <footer className="footer">
        <span>Skopeo {health ? `v${health.version}` : ""}</span>
        <span>Every finding cites evidence. Only red-team-verified findings are scored. Nothing reaches GitHub without approval.</span>
        <a href="/docs" target="_blank" rel="noreferrer">
          OpenAPI reference
        </a>
      </footer>
    </div>
  );
}
