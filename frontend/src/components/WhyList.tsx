import { css, zoneColor, zoneOf } from "@/lib/colors";
import type { Why, ZoneSpec } from "@/lib/types";

/** "Risk increase caused by: ✓ Reflectivity increased ..." */
export default function WhyList({ why, zones }: { why: Why | null; zones: ZoneSpec[] }) {
  if (!why) return <p className="text-xs text-slate-500">Loading…</p>;
  if (why.lag_min <= 0 || why.risk_before === null) {
    return <p className="text-xs text-slate-400">Collecting history. The comparison appears after a few frames.</p>;
  }
  const pts = Math.round(why.risk_delta * 100);
  const zBefore = zones[zoneOf(why.risk_before, zones)];
  const zNow = zones[zoneOf(why.risk_now, zones)];
  const heading =
    why.direction === "up" ? "Risk increase caused by:" :
    why.direction === "down" ? "Risk decrease caused by:" : "Risk is holding steady";
  const tone = why.direction === "up" ? "text-red-300" : why.direction === "down" ? "text-sky-300" : "text-slate-300";
  const mark = why.direction === "down" ? "↓" : "✓";

  return (
    <div className="text-xs">
      <div className="flex items-center gap-1.5 text-slate-200">
        <span className="h-2 w-2 rounded-full" style={{ background: css(zoneColor(why.risk_before, zones, 255)) }} />
        {Math.round(why.risk_before * 100)}%
        <span className="text-slate-500">→</span>
        <span className="h-2 w-2 rounded-full" style={{ background: css(zoneColor(why.risk_now, zones, 255)) }} />
        {Math.round(why.risk_now * 100)}%
        <span className={`tabular-nums ${tone}`}>({pts > 0 ? "+" : ""}{pts} pts)</span>
        <span className="text-slate-500">in {why.lag_min.toFixed(0)} min</span>
      </div>
      {zBefore.key !== zNow.key && (
        <div className="mt-0.5 text-slate-400">Zone changed: {zBefore.label} → {zNow.label}</div>
      )}
      <div className={`mt-2 font-medium ${tone}`}>{heading}</div>
      {why.direction !== "steady" && (
        why.drivers.length ? (
          <ul className="mt-1 space-y-1">
            {why.drivers.map((d) => (
              <li key={d.key} className="flex gap-2">
                <span className={tone} aria-hidden>{mark}</span>
                <span>
                  <span className="text-slate-100">{d.text}</span>
                  <span className="block text-[11px] text-slate-400">{d.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-slate-400">No single factor crossed its threshold; many small changes added up.</p>
        )
      )}
    </div>
  );
}