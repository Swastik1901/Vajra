"use client";
import { useState } from "react";
import { getJson } from "@/lib/api";
import type { Frame } from "@/lib/types";

const DOT: Record<string, string> = { ok: "bg-emerald-400", noisy: "bg-amber-400", "partial outage": "bg-amber-400", outage: "bg-red-500" };
const MIX_ORDER = ["observed", "proxy", "persistence", "neighbour fill", "default"];

const DEMOS: [string, string, string][] = [
  ["radar", "outage", "Radar outage"],
  ["satellite", "noisy", "Satellite noise"],
  ["lightning", "outage", "Lightning dropout"],
];

/** Which sensors are healthy, how the gaps were filled, and buttons to break a sensor on purpose. */
export default function SensorHealth({ frame }: { frame: Frame }) {
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); } catch {} finally { setBusy(false); } };
  const inject = (source: string, mode: string) => act(() => getJson("/api/faults", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source, mode, duration_ticks: 30 }),
  }));
  const clear = () => act(() => getJson("/api/faults", { method: "DELETE" }));
  const q = frame.fusion;
  const degraded = frame.sensors.some((s) => s.status !== "ok");

  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-72 text-xs">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-sm text-slate-100">Sensor reliability</h2>
        <span className="text-slate-400">data quality {Math.round(q.mean_quality * 100)}%</span>
      </div>
      <ul className="mt-2 space-y-1">
        {frame.sensors.map((s) => (
          <li key={s.source} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-slate-200">
              <span className={`h-2 w-2 rounded-full ${DOT[s.status]}`} />{s.label}
            </span>
            <span className="text-slate-400">
              {s.status === "ok" ? "healthy" : s.status === "noisy" ? `noisy ×${s.noise_mult}` : `${s.status}, ${s.availability_pct}% coverage`}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-2 text-[11px] text-slate-400">
        Inputs: {MIX_ORDER.filter((k) => (q.mix[k] ?? 0) > 0.05).map((k) => `${Math.round(q.mix[k])}% ${k}`).join(" · ")}
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer text-slate-300">{degraded ? "Fault controls (active)" : "Try breaking a sensor"}</summary>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {DEMOS.map(([src, mode, label]) => (
            <button key={label} disabled={busy} onClick={() => inject(src, mode)}
              className="rounded-full border border-white/15 px-2.5 py-1 text-slate-200 hover:bg-white/10 disabled:opacity-50 focus:outline-none focus-visible:ring-2 ring-orange-400">{label}</button>
          ))}
          <button disabled={busy} onClick={clear}
            className="rounded-full border border-emerald-400/40 px-2.5 py-1 text-emerald-300 hover:bg-white/10 disabled:opacity-50 focus:outline-none focus-visible:ring-2 ring-orange-400">Clear faults</button>
        </div>
        <p className="mt-2 text-[11px] leading-snug text-slate-500">
          Gaps are filled from other sensors, neighbours or the last good value, and every filled input is marked less reliable, which widens the forecast range.
        </p>
      </details>
    </div>
  );
}