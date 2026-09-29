import { css, riskColor } from "@/lib/colors";
import { METRICS, targetIndex } from "@/lib/metrics";
import type { AppConfig, MetricKey } from "@/lib/types";

export default function HazardLegend({ metric, config }: { metric: MetricKey; config: AppConfig }) {
  const stops = Array.from({ length: 12 }, (_, i) => css(riskColor(i / 11).map((v, k) => (k === 3 ? Math.max(v, 120) : v)) as any));
  const label = METRICS.find((m) => m.key === metric)!.label;
  const spec = metric === "risk" ? null : config.targets[targetIndex(metric)];
  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-64 text-xs">
      <div className="font-medium text-slate-100 mb-2">{label}</div>
      <div className="h-2.5 rounded-full" style={{ background: `linear-gradient(90deg, ${stops.join(",")})` }} />
      <div className="flex justify-between mt-1 text-slate-400">
        <span>{spec ? `${spec.lo}` : "Low"}</span>
        <span>{spec ? `${spec.hi} ${spec.unit}` : "Severe"}</span>
      </div>
      {metric === "risk" && (
        <p className="mt-2 text-slate-400 leading-snug">
          Worst of lightning, hail, downburst and cloudburst in each cell. Magenta means an active severe core.
        </p>
      )}
    </div>
  );
}
