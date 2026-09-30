import type { ZoneSpec } from "./types";

export type RGBA = [number, number, number, number];

// white/blue (low) -> yellow -> orange -> red -> magenta (extreme)
const STOPS: { at: number; c: RGBA }[] = [
  { at: 0.0, c: [96, 165, 250, 28] },
  { at: 0.18, c: [219, 234, 254, 95] },
  { at: 0.38, c: [253, 224, 71, 165] },
  { at: 0.58, c: [251, 146, 60, 200] },
  { at: 0.8, c: [239, 68, 68, 225] },
  { at: 1.0, c: [217, 70, 239, 240] },
];

export function riskColor(v: number): RGBA {
  const x = Math.max(0, Math.min(1, v));
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i].at) {
      const a = STOPS[i - 1], b = STOPS[i];
      const t = (x - a.at) / (b.at - a.at);
      return [0, 1, 2, 3].map((k) => Math.round(a.c[k] + (b.c[k] - a.c[k]) * t)) as RGBA;
    }
  }
  return STOPS[STOPS.length - 1].c;
}

export const HEAT_RANGE: [number, number, number, number][] = [
  [96, 165, 250, 0], [186, 220, 253, 90], [253, 224, 71, 150],
  [251, 146, 60, 190], [239, 68, 68, 220], [217, 70, 239, 240],
];

export const css = (c: RGBA) => `rgba(${c[0]},${c[1]},${c[2]},${(c[3] / 255).toFixed(2)})`;

// ---- categorical warning zones (Blue / Green / Yellow / Orange / Red / Purple) ----
const ZONE_ALPHA = [55, 105, 150, 185, 215, 235];

export function zoneOf(v: number, zones: ZoneSpec[]): number {
  let z = 0;
  for (let i = 0; i < zones.length; i++) if (v >= zones[i].min) z = i;
  return z;
}

export function zoneColor(v: number, zones: ZoneSpec[], alpha?: number): RGBA {
  const i = zoneOf(v, zones);
  const [r, g, b] = zones[i].color;
  return [r, g, b, alpha ?? ZONE_ALPHA[i] ?? 200];
}