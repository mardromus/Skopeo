import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/aperture";

/** Counts from the previous value to the new one, so arriving evidence is felt rather than flashed. */
export function AnimatedNumber({ value, decimals = 0, duration = 650 }: { value: number; decimals?: number; duration?: number }) {
  const reduced = prefersReducedMotion();
  const [shown, setShown] = useState(0);
  const fromRef = useRef(0);

  useEffect(() => {
    if (reduced) return;
    const from = fromRef.current;
    if (from === value) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const v = from + (value - from) * (1 - Math.pow(1 - t, 3));
      fromRef.current = v;
      setShown(v);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduced]);

  return <span className="num">{(reduced ? value : shown).toFixed(decimals)}</span>;
}
