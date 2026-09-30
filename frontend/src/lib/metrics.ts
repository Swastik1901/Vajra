import type { AppConfig, JoinedCell, MetricKey } from "./types";

export const METRICS: { key: MetricKey; label: string }[] = [
  { key: "risk", label: "Combined risk" },
  { key: "lightning", label: "Lightning" },
  { key: "hail", label: "Hail" },
  { key: "downburst", label: "Downburst" },
  { key: "cloudburst", label: "Cloudburst" },
];

const TARGET_INDEX: Record<string, number> = { lightning: 0, hail: 1, downburst: 2, cloudburst: 3 };
export const targetIndex = (k: MetricKey) => TARGET_INDEX[k];

/** 0..1 intensity used for colouring, for the chosen metric. */
export function metricValue(c: JoinedCell, metric: MetricKey, config: AppConfig): number {
  if (metric === "risk") return c.r;
  const i = TARGET_INDEX[metric];
  const s = config.targets[i];
  return Math.max(0, Math.min(1, (c.t[i] - s.lo) / (s.hi - s.lo)));
}

export const FEATURE_META: Record<string, { label: string; unit: string }> = {
  dbz: { label: "Reflectivity", unit: "dBZ" },
  vil: { label: "Vertically integrated liquid", unit: "kg/m²" },
  cth_k: { label: "Cloud-top temperature", unit: "K" },
  cooling_k15: { label: "Cloud-top cooling", unit: "K/15 min" },
  cape: { label: "CAPE", unit: "J/kg" },
  wind_u: { label: "Wind, eastward", unit: "m/s" },
  wind_v: { label: "Wind, northward", unit: "m/s" },
  lightning: { label: "Recent lightning pulses", unit: "count" },
  humidity: { label: "Relative humidity", unit: "%" },
};

export const bearingDeg = (u: number, v: number) => (Math.atan2(u, v) * 180 / Math.PI + 360) % 360;
export const compass = (deg: number) =>
  ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(deg / 45) % 8];

export function fmtMinutes(m: number) {
  if (m < 1) return "now";
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return h ? `${h} h ${r} min` : `${r} min`;
}

export const placeLabel = (n: { name: string; distance_km: number; bearing: string }) =>
  n.distance_km < 5 ? `In ${n.name}` : `${Math.round(n.distance_km)} km ${n.bearing} of ${n.name}`;