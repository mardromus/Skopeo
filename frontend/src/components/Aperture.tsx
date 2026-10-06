import { useEffect, useId, useState } from "react";
import { BLADES, OUTER, aperturePaths, openingRadius, prefersReducedMotion } from "../lib/aperture";

export interface ApertureProps {
  size?: number;
  /** resting openness, 0 (closed) … 1 (wide open) */
  openness?: number;
  /** agents working: the iris turns slowly and breathes */
  live?: boolean;
  /** ambient: the opening breathes without turning */
  breathe?: boolean;
  /** colour of the gaps between blades (the surface behind the mark) */
  gap?: string;
  /** open from almost closed when first shown */
  intro?: boolean;
  /** per-blade fills; defaults to a tonal sweep of the signal colour */
  fills?: string[];
  ring?: boolean;
  focus?: boolean;
  title?: string;
  className?: string;
  onBladeHover?: (index: number | null) => void;
  highlight?: number | null;
}

const TONES = Array.from({ length: BLADES }, (_, i) => `color-mix(in oklab, var(--signal) ${100 - i * 6}%, var(--ink) ${i * 6}%)`);
const ease = (t: number) => 1 - Math.pow(1 - t, 3);

/** Skopeo's iris mark, rendered from live geometry so it can open, focus and turn. */
export function Aperture({ size = 28, openness = 0.42, live = false, breathe = false, gap = "var(--surface)", intro = true, fills, ring = true, focus = true, title, className, onBladeHover, highlight = null }: ApertureProps) {
  const gid = useId().replace(/:/g, "");
  const reduced = prefersReducedMotion();
  const [state, setState] = useState(() => ({ open: intro && !reduced ? 0.04 : openness, rot: -Math.PI / 2 }));

  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const start = performance.now();
    const from = state.open;
    const tick = (now: number) => {
      const t = (now - start) / 1000;
      const introT = Math.min(1, t / 1.1);
      let open = from + (openness - from) * ease(introT);
      let rot = -Math.PI / 2 + (1 - ease(introT)) * -0.9;
      if (live || breathe) open += Math.sin(t * (live ? 2.2 : 0.9)) * (live ? 0.07 : 0.035) * introT;
      if (live) rot += t * 0.32;
      setState({ open, rot });
      if (live || breathe || introT < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, breathe, openness, reduced]);

  const view = reduced ? { open: openness, rot: -Math.PI / 2 } : state;
  const blades = aperturePaths(openingRadius(view.open), view.rot);
  const pad = ring ? 7 : 1;
  const vb = OUTER + pad;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={`${-vb} ${-vb} ${vb * 2} ${vb * 2}`}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        <radialGradient id={`sheen-${gid}`} cx="0" cy="0" r={OUTER} gradientUnits="userSpaceOnUse">
          <stop offset="0.25" stopColor="var(--ink)" stopOpacity="0.28" />
          <stop offset="1" stopColor="var(--ink)" stopOpacity="0" />
        </radialGradient>
      </defs>
      {ring && <circle r={OUTER + 4} fill="none" stroke="var(--ink)" strokeWidth={size < 40 ? 4.2 : 2.2} />}
      <g>
        {blades.map((b, i) => (
          <path
            key={i}
            d={b.d}
            fill={(fills ?? TONES)[i % (fills ?? TONES).length]}
            stroke={gap}
            strokeWidth={size < 40 ? 2.4 : 1.3}
            strokeLinejoin="round"
            opacity={highlight === null || highlight === i ? 1 : 0.35}
            style={{ transition: "opacity .2s ease" }}
            onMouseEnter={onBladeHover ? () => onBladeHover(i) : undefined}
            onMouseLeave={onBladeHover ? () => onBladeHover(null) : undefined}
          />
        ))}
        {blades.map((b, i) => (
          <path key={`s${i}`} d={b.d} fill={`url(#sheen-${gid})`} pointerEvents="none" />
        ))}
      </g>
      {focus && <circle r={Math.max(2.4, openingRadius(view.open) * 0.32)} fill="var(--ink)" />}
    </svg>
  );
}
