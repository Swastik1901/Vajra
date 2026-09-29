"use client";
import { useEffect, useState } from "react";
import type { AppConfig, Frame } from "@/lib/types";

const HAZARD: Record<string, string> = {
  lightning: "Lightning", hail: "Hail", downburst: "Downburst", cloudburst: "Cloudburst",
};

function fmt(sec: number) {
  if (sec <= 0) return "Overhead";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.floor(sec % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

export default function ETACountdown({ frame, config }: { frame: Frame; config: AppConfig }) {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    const t = setInterval(() => setNow(performance.now()), 500);
    return () => clearInterval(t);
  }, []);
  const elapsed = (now - (frame.receivedAt ?? now)) / 1000;

  return (
    <div className="rounded-xl bg-slate-900/85 backdrop-blur border border-white/10 p-3 w-72 text-sm">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-slate-100">Storm arrival</h2>
        <span className="text-[11px] text-slate-400">clock runs ×{config.time_lapse.toFixed(0)}</span>
      </div>
      {frame.etas.length === 0 ? (
        <p className="mt-2 text-slate-400 text-xs">No storm is heading for a monitored place in the next 6 hours.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {frame.etas.slice(0, 6).map((e) => {
            const remaining = e.eta_min * 60 - elapsed * config.time_lapse;
            return (
              <li key={e.place} className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-slate-100">{e.place}</div>
                  <div className="text-[11px] text-slate-400">{HAZARD[e.hazard] ?? e.hazard} · storm #{e.storm_id}</div>
                </div>
                <div className={`tabular-nums font-medium ${remaining <= 900 ? "text-red-400" : remaining <= 3600 ? "text-orange-300" : "text-slate-200"}`}>
                  {fmt(remaining)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
