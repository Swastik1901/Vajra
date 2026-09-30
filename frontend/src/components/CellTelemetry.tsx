"use client";
import { compass, bearingDeg, FEATURE_META } from "@/lib/metrics";
import { css, riskColor } from "@/lib/colors";
import { useCellExplain } from "@/hooks/useCellExplain";
import WhyList from "./WhyList";
import RegionSummary from "./RegionSummary";
import { zoneColor, zoneOf } from "@/lib/colors";
import { placeLabel } from "@/lib/metrics";
import type { AppConfig, Frame, JoinedCell, PointInfo } from "@/lib/types";

export default function CellTelemetry({
  cell, config, frame, point, onClose,
}: { cell: JoinedCell; config: AppConfig; frame: Frame; point?: PointInfo | null; onClose: () => void }) {
  const why = useCellExplain(cell.i, frame.tick);
  const zone = config.zones[zoneOf(cell.r, config.zones)];
  const speed = Math.hypot(cell.w[0], cell.w[1]);
  const dir = bearingDeg(cell.w[0], cell.w[1]);
  return (
    <div role="dialog" aria-label="Cell details"
      className="w-80 max-h-[80vh] overflow-auto rounded-xl bg-slate-900/95 backdrop-blur border border-white/15 p-4 text-sm shadow-2xl">
      <div className="flex items-start justify-between">
        <div>
          <div className="font-medium text-slate-100">{point ? placeLabel(point.nearest) : `Cell ${cell.id}`}</div>
          <div className="text-[11px] text-slate-400">
            {(point?.lat ?? cell.centroid[1]).toFixed(3)}°N, {(point?.lon ?? cell.centroid[0]).toFixed(3)}°E · cell {cell.id}
          </div>
        </div>
        <button onClick={onClose} className="rounded px-2 py-0.5 text-slate-300 hover:bg-white/10 focus:outline-none focus-visible:ring-2 ring-orange-400">Close</button>
      </div>

      {point && <RegionSummary point={point} config={config} />}

      <div className="mt-3 flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: css(zoneColor(cell.r, config.zones, 255)) }} />
        <span className="text-slate-100">{zone.label} · risk {(cell.r * 100).toFixed(0)}%</span>
        <span className="text-slate-400 text-xs">{frame.horizon > 0 ? `forecast +${frame.horizon} min` : "now"}</span>
      </div>

      <div className="mt-1 text-xs text-slate-400">{zone.advice}</div>

      <h3 className="mt-4 mb-1 text-xs text-slate-400">Why is risk changing here</h3>
      <WhyList why={why} zones={config.zones} />

      <h3 className="mt-4 mb-1 text-xs text-slate-400">Model output</h3>
      {config.targets.map((t, i) => {
        const n = Math.max(0, Math.min(1, (cell.t[i] - t.lo) / (t.hi - t.lo)));
        return (
          <div key={t.key} className="mb-2">
            <div className="flex justify-between"><span>{t.label}</span><span className="tabular-nums">{cell.t[i].toFixed(1)} {t.unit}</span></div>
            <div className="h-1.5 rounded bg-white/10"><div className="h-1.5 rounded" style={{ width: `${n * 100}%`, background: css(riskColor(n)) }} /></div>
          </div>
        );
      })}

      <h3 className="mt-4 mb-1 text-xs text-slate-400">Wind</h3>
      <div>{speed.toFixed(1)} m/s ({(speed * 3.6).toFixed(0)} km/h) from the {compass((dir + 180) % 360)}, moving {compass(dir)}</div>

      <h3 className="mt-4 mb-1 text-xs text-slate-400">Latest observations (model inputs)</h3>
      <table className="w-full text-xs">
        <tbody>
          {config.features.map((f, i) => (
            <tr key={f} className="border-t border-white/5">
              <td className="py-1 text-slate-300">{FEATURE_META[f]?.label ?? f}</td>
              <td className="py-1 text-right tabular-nums">{cell.x[i]} <span className="text-slate-500">{FEATURE_META[f]?.unit}</span></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="mt-4 mb-1 text-xs text-slate-400">Inference</h3>
      <div className="text-xs text-slate-300">
        {frame.model.name} v{frame.model.version} · {frame.inference_ms} ms across {frame.n_chunks} chunks · tick {frame.tick}
      </div>
    </div>
  );
}