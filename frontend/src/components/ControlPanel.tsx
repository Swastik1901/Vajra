"use client";
import { METRICS, fmtMinutes } from "@/lib/metrics";
import type { AppConfig, Frame, LayerToggles, MetricKey } from "@/lib/types";
import type { StreamStatus } from "@/hooks/useNowcastStream";

interface Props {
  config: AppConfig; frame: Frame | null; status: StreamStatus;
  metric: MetricKey; setMetric: (m: MetricKey) => void;
  horizon: number; setHorizon: (h: number) => void;
  layers: LayerToggles; setLayers: (l: LayerToggles) => void;
  dark: boolean; setDark: (d: boolean) => void;
}

const LAYER_LABELS: [keyof LayerToggles, string][] = [
  ["hex", "Risk cells"], ["heat", "Heat glow"], ["particles", "Wind particles"],
  ["arrows", "Drift arrows"], ["storms", "Storm cells"], ["places", "Places"],
];

export default function ControlPanel(p: Props) {
  const { config, frame, status } = p;
  const dot = status === "live" ? "bg-emerald-400" : status === "connecting" ? "bg-amber-400" : "bg-red-500";
  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-4 w-72 text-sm space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${dot}`} />
          <h1 className="font-medium text-slate-100">Storm nowcast, 0–6 h</h1>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {status === "live" && frame ? `Live · ${new Date(frame.sim_time).toUTCString().slice(17, 25)} UTC (simulated)` :
            status === "connecting" ? "Connecting to the API…" : "Disconnected. Retrying…"}
        </div>
      </div>

      {frame && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          {config.targets.map((t, i) => (
            <div key={t.key} className="rounded-lg bg-white/5 px-2 py-1.5">
              <div className="text-slate-400">Peak {t.key}</div>
              <div className="text-slate-100 tabular-nums">{frame.stats.max[i].toFixed(0)} <span className="text-slate-500">{t.unit}</span></div>
            </div>
          ))}
          <div className="rounded-lg bg-white/5 px-2 py-1.5">
            <div className="text-slate-400">High-risk cells</div>
            <div className="text-slate-100 tabular-nums">{frame.stats.high_cells} <span className="text-slate-500">/ {frame.stats.n_cells}</span></div>
          </div>
          <div className="rounded-lg bg-white/5 px-2 py-1.5">
            <div className="text-slate-400">Inference</div>
            <div className="text-slate-100 tabular-nums">{frame.inference_ms} ms</div>
          </div>
        </div>
      )}

      <div>
        <div className="mb-1 flex justify-between text-xs">
          <label htmlFor="horizon" className="text-slate-300">Forecast lead time</label>
          <span className="text-slate-100 tabular-nums">{p.horizon === 0 ? "Now" : `+${fmtMinutes(p.horizon)}`}</span>
        </div>
        <input id="horizon" type="range" min={0} max={360} step={15} value={p.horizon} className="w-full"
          onChange={(e) => p.setHorizon(Number(e.target.value))} />
      </div>

      <div>
        <div className="mb-1 text-xs text-slate-300">Colour by</div>
        <div className="flex flex-wrap gap-1.5">
          {METRICS.map((m) => (
            <button key={m.key} onClick={() => p.setMetric(m.key)} aria-pressed={p.metric === m.key}
              className={`rounded-full px-2.5 py-1 text-xs border focus:outline-none focus-visible:ring-2 ring-orange-400 ${
                p.metric === m.key ? "bg-orange-500 border-orange-400 text-slate-950" : "border-white/15 text-slate-300 hover:bg-white/10"}`}>
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1 text-xs text-slate-300">Layers</div>
        <div className="grid grid-cols-2 gap-1">
          {LAYER_LABELS.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-xs text-slate-200">
              <input type="checkbox" checked={p.layers[k]} onChange={(e) => p.setLayers({ ...p.layers, [k]: e.target.checked })} />
              {label}
            </label>
          ))}
        </div>
        <label className="mt-2 flex items-center gap-2 text-xs text-slate-200">
          <input type="checkbox" checked={!p.dark} onChange={(e) => p.setDark(!e.target.checked)} /> Light basemap
        </label>
      </div>

      <div className="text-[11px] text-slate-500 leading-snug">
        {config.n_cells.toLocaleString()} H3 cells (res {config.h3_res}) in {config.n_chunks} chunks · model {config.model.name}
      </div>
    </div>
  );
}
