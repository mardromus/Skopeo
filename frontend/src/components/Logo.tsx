import { Aperture } from "./Aperture";

/** Mark + wordmark. The iris turns while any investigation is live. */
export function Logo({ live = false, size = 30 }: { live?: boolean; size?: number }) {
  return (
    <span className="logo">
      <Aperture size={size} live={live} title="Skopeo" />
      <span className="logo-type">
        <span className="logo-word">Skopeo</span>
        <span className="logo-tag">repository intelligence</span>
      </span>
    </span>
  );
}
