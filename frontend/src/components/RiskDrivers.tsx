"use client";
import { css, zoneColor, zoneOf } from "@/lib/colors";
import type { AppConfig, Storm } from "@/lib/types";
import WhyList from "./WhyList";

interface Props {
  storms: Storm[];
  config: AppConfig;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

/** Explains the change in the forecast for one storm: which inputs pushed the risk up or down. */
export default function RiskDrivers({ storms, config, selectedId, onSelect }: Props) {
  const sorted = [...storms].sort((a, b) => b.risk - a.risk);
  const storm = storms.find((s) => s.id === selectedId) ?? sorted[0];

  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-72 text-sm">
      <h2 className="font-medium text-slate-100">Why the risk is changing</h2>
      {!storm ? (
        <p className="mt-2 text-xs text-slate-400">No active storm cell right now. Zones show background risk only.</p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Choose storm">
            {sorted.slice(0, 6).map((s) => (
              <button key={s.id} onClick={() => onSelect(s.id)} aria-pressed={s.id === storm.id}
                className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 ring-orange-400 ${
                  s.id === storm.id ? "border-white/60 bg-white/10 text-slate-100" : "border-white/15 text-slate-300 hover:bg-white/10"}`}>
                <span className="h-2 w-2 rounded-full" style={{ background: css(zoneColor(s.risk, config.zones, 255)) }} />
                #{s.id}
              </button>
            ))}
          </div>
          <div className="mt-2 mb-2 text-xs text-slate-400">
            Storm #{storm.id} · {config.zones[zoneOf(storm.risk, config.zones)].label} · {Math.round(storm.speed_kmh)} km/h
          </div>
          <WhyList why={storm.why} zones={config.zones} />
        </>
      )}
    </div>
  );
}