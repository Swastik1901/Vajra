"use client";
import { useEffect, useRef, useState } from "react";
import type { AppConfig, JoinedCell } from "@/lib/types";

const COUNT = 1400;
const TRAIL = 12;
const VISUAL_SPEEDUP = 1800; // 1 real second ≈ 30 min of wind travel: purely visual
export const TRAIL_TIMESTAMPS = Array.from({ length: TRAIL }, (_, i) => i);

export interface Trail { path: [number, number][]; speed: number }
interface P { hist: [number, number][]; age: number; max: number; speed: number }

const rand = (a: number, b: number) => a + Math.random() * (b - a);

/** Animated particles advected through the live wind field (one field sample per hex cell). */
export function useWindParticles(cells: JoinedCell[] | null, config: AppConfig | null, enabled: boolean) {
  const [trails, setTrails] = useState<Trail[]>([]);
  const field = useRef<Map<string, [number, number, number]>>(new Map());
  const bin = useRef(0.06);

  useEffect(() => {
    if (!cells || !config) return;
    const b = config.cell_spacing_deg * 1.3;
    bin.current = b;
    const m = new Map<string, [number, number, number]>();
    for (const c of cells) {
      const k = `${Math.floor(c.centroid[0] / b)}:${Math.floor(c.centroid[1] / b)}`;
      const e = m.get(k) ?? [0, 0, 0];
      e[0] += c.w[0]; e[1] += c.w[1]; e[2] += 1;
      m.set(k, e);
    }
    field.current = m;
  }, [cells, config]);

  useEffect(() => {
    if (!enabled || !config) { setTrails([]); return; }
    const [minLon, minLat, maxLon, maxLat] = config.bbox;
    const spawn = (): P => {
      const pos: [number, number] = [rand(minLon, maxLon), rand(minLat, maxLat)];
      return { hist: Array.from({ length: TRAIL }, () => pos), age: 0, max: 70 + Math.random() * 90, speed: 0 };
    };
    const ps: P[] = Array.from({ length: COUNT }, () => { const p = spawn(); p.age = Math.random() * p.max; return p; });

    let raf = 0, last = 0;
    const loop = (t: number) => {
      raf = requestAnimationFrame(loop);
      if (t - last < 33) return;
      const dt = Math.min((t - last) / 1000, 0.1);
      last = t;
      const b = bin.current;
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i];
        const [lon, lat] = p.hist[TRAIL - 1];
        const e = field.current.get(`${Math.floor(lon / b)}:${Math.floor(lat / b)}`);
        if (!e || p.age > p.max) { ps[i] = spawn(); continue; }
        const u = e[0] / e[2], v = e[1] / e[2];
        const nlat = lat + (v * dt * VISUAL_SPEEDUP) / 111320;
        const nlon = lon + (u * dt * VISUAL_SPEEDUP) / (111320 * Math.cos((lat * Math.PI) / 180));
        p.hist = [...p.hist.slice(1), [nlon, nlat]];
        p.speed = Math.hypot(u, v);
        p.age += 1;
      }
      setTrails(ps.map((p) => ({ path: p.hist, speed: p.speed })));
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [enabled, config]);

  return trails;
}
