/**
 * Geometry for Skopeo's mark: an iris aperture of eight blades — one per specialist agent.
 *
 * The opening is a regular polygon of radius `r`. Each polygon edge is extended until it meets
 * the outer circle (radius R); blade i is the curved triangle between the extensions of edges
 * i and i+1. Shrinking `r` closes the iris, growing it opens the iris.
 */
export const BLADES = 8;
export const OUTER = 48;

export interface Blade {
  d: string;
  /** angle (radians) of the blade's centroid, for placing labels */
  mid: number;
}

const fmt = (p: readonly [number, number]) => `${p[0].toFixed(2)} ${p[1].toFixed(2)}`;

export function aperturePaths(opening: number, rotation = -Math.PI / 2, n = BLADES, R = OUTER): Blade[] {
  const r = Math.min(R * 0.86, Math.max(0.6, opening));
  const V = Array.from({ length: n }, (_, i) => {
    const a = rotation + (i * 2 * Math.PI) / n;
    return [r * Math.cos(a), r * Math.sin(a)] as const;
  });
  const P = V.map((v, i) => {
    const w = V[(i + 1) % n];
    const dx = w[0] - v[0];
    const dy = w[1] - v[1];
    const len = Math.hypot(dx, dy);
    const ux = dx / len;
    const uy = dy / len;
    const b = w[0] * ux + w[1] * uy;
    const c = w[0] * w[0] + w[1] * w[1] - R * R;
    const t = -b + Math.sqrt(Math.max(0, b * b - c));
    return [w[0] + t * ux, w[1] + t * uy] as const;
  });
  return V.map((_, i) => {
    const a = V[(i + 1) % n];
    const p = P[i];
    const q = P[(i + 1) % n];
    const cx = (a[0] + p[0] + q[0]) / 3;
    const cy = (a[1] + p[1] + q[1]) / 3;
    return { d: `M${fmt(a)} L${fmt(p)} A${R} ${R} 0 0 1 ${fmt(q)} Z`, mid: Math.atan2(cy, cx) };
  });
}

/** Map a 0..1 "openness" to an inner radius. */
export function openingRadius(openness: number, R = OUTER): number {
  return 3 + (R * 0.62 - 3) * Math.min(1, Math.max(0, openness));
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
