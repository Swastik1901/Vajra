import { css, zoneColor, zoneOf } from "@/lib/colors";
import { fmtMinutes } from "@/lib/metrics";
import type { AppConfig, PointInfo } from "@/lib/types";

const LABEL = (m: number) => (m === 0 ? "Now" : m < 60 ? `+${m}m` : `+${m / 60}h`);
const HAZARD: Record<string, string> = { lightning: "lightning", hail: "hail", downburst: "damaging gusts", cloudburst: "a cloudburst" };

/** Plain-language outlook for the clicked spot: next 6 hours + any storm heading here. */
export default function RegionSummary({ point, config }: { point: PointInfo; config: AppConfig }) {
  if (!point.forecast.length) return null;
  const z = config.zones;
  const peak = point.forecast.reduce((a, b) => (b.risk > a.risk ? b : a));
  const peakZone = z[zoneOf(peak.risk, z)];
  const calm = zoneOf(peak.risk, z) <= 2; // blue / green / yellow
  const arrival = point.arrivals[0];

  return (
    <div className="mt-3 rounded-lg bg-white/5 p-2.5 text-xs">
      <div className="text-slate-100">
        {calm
          ? "No significant storm expected here in the next 6 hours."
          : `${peakZone.label.split(" · ")[1]} conditions expected ${peak.minutes === 0 ? "now" : `around ${LABEL(peak.minutes)}`}.`}
      </div>
      {arrival && (
        <div className="mt-1 text-orange-300">
          Storm #{arrival.storm_id} ({HAZARD[arrival.hazard] ?? arrival.hazard}) {arrival.eta_min < 1 ? "is overhead" : `reaches here in about ${fmtMinutes(arrival.eta_min)}`}.
        </div>
      )}
      <div className="mt-2 flex items-end gap-1" role="img" aria-label="Risk outlook for the next 6 hours">
        {point.forecast.map((f) => (
          <div key={f.minutes} className="flex flex-1 flex-col items-center gap-1">
            <div className="flex h-12 w-full items-end rounded-sm bg-white/5">
              <div className="w-full rounded-sm" style={{ height: `${Math.max(6, f.risk * 100)}%`, background: css(zoneColor(f.risk, z, 255)) }} />
            </div>
            <span className="text-[9px] text-slate-400">{LABEL(f.minutes)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}