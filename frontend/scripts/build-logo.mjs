// Renders Skopeo's aperture mark to static SVG files (favicon + docs logo).
// Same geometry as src/lib/aperture.ts; run with `node scripts/build-logo.mjs`.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const R = 48;
const N = 8;
const fmt = (p) => `${p[0].toFixed(2)} ${p[1].toFixed(2)}`;

function blades(r, rot = -Math.PI / 2) {
  const V = Array.from({ length: N }, (_, i) => {
    const a = rot + (i * 2 * Math.PI) / N;
    return [r * Math.cos(a), r * Math.sin(a)];
  });
  const P = V.map((v, i) => {
    const w = V[(i + 1) % N];
    const dx = w[0] - v[0];
    const dy = w[1] - v[1];
    const len = Math.hypot(dx, dy);
    const ux = dx / len;
    const uy = dy / len;
    const b = w[0] * ux + w[1] * uy;
    const c = w[0] ** 2 + w[1] ** 2 - R * R;
    const t = -b + Math.sqrt(b * b - c);
    return [w[0] + t * ux, w[1] + t * uy];
  });
  return V.map((_, i) => `M${fmt(V[(i + 1) % N])} L${fmt(P[i])} A${R} ${R} 0 0 1 ${fmt(P[(i + 1) % N])} Z`);
}

// tonal sweep from petrol to deep petrol, matching the app's colour-mix
const tones = ["#0c6870", "#0b636b", "#0b5e66", "#0a5961", "#0a545b", "#094f56", "#094a51", "#08454b"];

function mark({ ring = true, background = null, size = 128 } = {}) {
  const r = 3 + (R * 0.62 - 3) * 0.42;
  const vb = R + 7;
  const paths = blades(r)
    .map((d, i) => `<path d="${d}" fill="${tones[i]}" stroke="${background ?? "#ffffff"}" stroke-width="2.2" stroke-linejoin="round"/>`)
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${-vb} ${-vb} ${vb * 2} ${vb * 2}" role="img" aria-label="Skopeo">
${background ? `<circle r="${vb}" fill="${background}"/>` : `<circle r="${R + 3}" fill="#ffffff"/>`}
${ring ? `<circle r="${R + 4}" fill="none" stroke="#14181e" stroke-width="4"/>` : ""}
${paths}
<circle r="${(r * 0.32).toFixed(2)}" fill="#14181e"/>
</svg>
`;
}

const targets = {
  [resolve(here, "../public/favicon.svg")]: mark({ size: 64 }),
  [resolve(here, "../../docs/logo.svg")]: mark({ size: 128 }),
};
for (const [file, svg] of Object.entries(targets)) {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, svg);
  console.log("wrote", file);
}
