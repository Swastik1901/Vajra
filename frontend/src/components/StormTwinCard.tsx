import { css, zoneColor, zoneOf } from "@/lib/colors";
import { compass, confidenceLabel, fmtMinutes, pct } from "@/lib/metrics";
import type { AppConfig, EndedStorm, Stage, Storm } from "@/lib/types";

const STAGE: Record<Stage, { label: string; tone: string }> = {
  initiating: { label: "Initiating", tone: "bg-sky-500/20 text-sky-200" },
  intensifying: { label: "Intensifying", tone: "bg-red-500/20 text-red-200" },
  mature: { label: "Mature", tone: "bg-orange-500/20 text-orange-200" },
  weakening: { label: "Weakening", tone: "bg-slate-500/30 text-slate-200" },
};

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return <div className="h-9 text-[11px] text-slate-500">History builds up as the storm is tracked.</div>;
  const w = 240, h = 36;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - Math.max(0, Math.min(1, v)) * (h - 4)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-full" role="img" aria-label="Risk history of this storm">
      <line x1="0" x2={w} y1={h - 2 - 0.5 * (h - 4)} y2={h - 2 - 0.5 * (h - 4)} stroke="rgba(255,255,255,.15)" strokeDasharray="3 3" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** One storm as a living object: lifecycle stage, intensity history, confidence, end-of-life estimate. */
export default function StormTwinCard({ storm, config, ended }: { storm: Storm; config: AppConfig; ended: EndedStorm[] }) {
  const tw = storm.twin;
  if (!tw) return null;
  const st = STAGE[tw.stage];
  const color = css(zoneColor(storm.risk, config.zones, 255));
  const zone = config.zones[zoneOf(storm.risk, config.zones)];
  const trend = tw.trend_per_10min;
  return (
    <div className="text-xs">
      <div className="flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 ${st.tone}`}>{st.label}</span>
        <span className="text-slate-400">tracked for {fmtMinutes(tw.observed_min)}</span>
      </div>
      <div className="mt-1 text-slate-300">
        Moving {compass(storm.bearing_deg)} at {Math.round(storm.speed_kmh)} km/h · {zone.label}
      </div>
      <div className="mt-2"><Sparkline values={tw.risk_hist} color={color} /></div>
      <div className="flex justify-between text-[10px] text-slate-500"><span>risk history</span><span>dashed line = Warning zone</span></div>

      <div className="mt-2 grid grid-cols-3 gap-1.5">
        <div className="rounded-lg bg-white/5 px-2 py-1"><div className="text-slate-400">Now</div><div className="text-slate-100 tabular-nums">{pct(storm.risk)}%</div></div>
        <div className="rounded-lg bg-white/5 px-2 py-1"><div className="text-slate-400">Peak</div><div className="text-slate-100 tabular-nums">{pct(tw.peak_risk)}%</div></div>
        <div className="rounded-lg bg-white/5 px-2 py-1"><div className="text-slate-400">Trend /10 min</div>
          <div className={`tabular-nums ${trend > 0.01 ? "text-red-300" : trend < -0.01 ? "text-sky-300" : "text-slate-100"}`}>{trend > 0 ? "+" : ""}{Math.round(trend * 100)} pts</div></div>
      </div>

      <div className="mt-2 text-slate-300">
        Risk {pct(storm.risk)}% (range {pct(storm.lo)}–{pct(storm.hi)}%), <b className="text-slate-100">{confidenceLabel(storm.conf)} confidence</b>
      </div>
      <div className="text-slate-400">
        {tw.eol_min !== null
          ? `Expected to drop below Warning in about ${fmtMinutes(tw.eol_min)} (based on its trend).`
          : "No weakening trend yet. The forecast assumes a typical remaining life for its stage."}
      </div>
      {ended.length > 0 && (
        <div className="mt-2 border-t border-white/10 pt-2 text-[11px] text-slate-400">
          Recently ended: {ended.slice(0, 3).map((e) => `#${e.id} (${fmtMinutes(e.lifetime_min)}, peak ${pct(e.peak_risk)}%)`).join(" · ")}
        </div>
      )}
    </div>
  );
}