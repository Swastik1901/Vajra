import { css, riskColor, zoneColor, zoneOf } from "@/lib/colors";
import { METRICS, metricValue, targetIndex } from "@/lib/metrics";
import type { AppConfig, ColorMode, JoinedCell, MetricKey } from "@/lib/types";

interface Props { metric: MetricKey; config: AppConfig; colorMode: ColorMode; cells: JoinedCell[] }

export default function HazardLegend({ metric, config, colorMode, cells }: Props) {
  const label = METRICS.find((m) => m.key === metric)!.label;
  const spec = metric === "risk" ? null : config.targets[targetIndex(metric)];
  const counts = new Array(config.zones.length).fill(0);
  for (const c of cells) counts[zoneOf(metricValue(c, metric, config), config.zones)]++;

  if (colorMode === "gradient") {
    const stops = Array.from({ length: 12 }, (_, i) => css(riskColor(i / 11).map((v, k) => (k === 3 ? Math.max(v, 120) : v)) as any));
    return (
      <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-64 text-xs">
        <div className="font-medium text-slate-100 mb-2">{label}</div>
        <div className="h-2.5 rounded-full" style={{ background: `linear-gradient(90deg, ${stops.join(",")})` }} />
        <div className="flex justify-between mt-1 text-slate-400">
          <span>{spec ? spec.lo : "Low"}</span><span>{spec ? `${spec.hi} ${spec.unit}` : "Severe"}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-72 text-xs">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-medium text-slate-100">Warning zones</span>
        <span className="text-slate-400">{label}{spec ? ` (${spec.unit})` : ""}</span>
      </div>
      <ul className="space-y-1.5">
        {config.zones.map((z, i) => ({ z, i })).reverse().map(({ z, i }) => (
          <li key={z.key} className="flex items-start gap-2">
            <span className="mt-0.5 h-3 w-3 shrink-0 rounded-sm" style={{ background: css(zoneColor(z.min, config.zones, 255)) }} />
            <span className="flex-1">
              <span className="text-slate-100">{z.label}</span>
              <span className="block text-[11px] leading-snug text-slate-400">{z.advice}</span>
            </span>
            <span className="tabular-nums text-slate-300">{counts[i] ? `${Math.round(counts[i] * config.cell_area_km2).toLocaleString()} km²` : "–"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}