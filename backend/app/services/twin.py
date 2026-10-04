"""Storm digital twin: one living record per storm (track, intensity history, lifecycle stage,
projected path with a growing uncertainty cone, estimated end of life)."""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from ..fusion.grid import HexGrid

KM_PER_DEG = 111.32
EOL_DEFAULT = {"initiating": 180.0, "intensifying": 150.0, "mature": 120.0, "weakening": 45.0}
_OFFS = [(0, 0), (0.15, 0), (-0.15, 0), (0, 0.15), (0, -0.15)]


def project_track(grid: HexGrid, u: np.ndarray, v: np.ndarray, s: dict, step: int = 10,
                  horizon: int = 360, every: int = 30) -> list[dict]:
    """Where the storm goes: step through the live wind field, blended with the storm's own motion."""
    lat, lon, r0 = s["lat"], s["lon"], s["radius_km"]
    su, sv = s["u"], s["v"]
    out = [{"m": 0, "lat": round(lat, 3), "lon": round(lon, 3), "radius_km": round(r0, 1)}]
    dist = 0.0
    for m in range(step, horizon + 1, step):
        la = np.array([lat + a for a, _ in _OFFS])
        lo = np.array([lon + b for _, b in _OFFS])
        idx = grid.lookup(la, lo)
        ok = idx >= 0
        uu = 0.5 * float(u[idx[ok]].mean()) + 0.5 * su if ok.any() else su
        vv = 0.5 * float(v[idx[ok]].mean()) + 0.5 * sv if ok.any() else sv
        lat += vv * step * 60 / 111320.0
        lon += uu * step * 60 / (111320.0 * math.cos(math.radians(lat)))
        dist += math.hypot(uu, vv) * step * 60 / 1000.0
        if m % every == 0:
            out.append({"m": m, "lat": round(lat, 3), "lon": round(lon, 3),
                        "radius_km": round(r0 * (1 + 0.1 * m / 60) + 0.12 * dist + 3, 1)})
    return out


def interp_track(track: list[dict], minutes: float) -> tuple[float, float]:
    ms = [t["m"] for t in track]
    return (float(np.interp(minutes, ms, [t["lat"] for t in track])),
            float(np.interp(minutes, ms, [t["lon"] for t in track])))


class TwinRegistry:
    def __init__(self):
        self.rec: dict[int, dict] = {}
        self.ended: deque[dict] = deque(maxlen=5)

    def update(self, storms: list[dict], grid: HexGrid, u: np.ndarray, v: np.ndarray, sim_min: float) -> None:
        alive = set()
        for s in storms:
            sid = s["id"]
            alive.add(sid)
            r = self.rec.get(sid)
            if r is None:
                r = {"born": sim_min, "track": deque(maxlen=60), "risk": deque(maxlen=60), "t": deque(maxlen=60),
                     "peak_risk": 0.0, "peak": np.zeros(4)}
                self.rec[sid] = r
            r["track"].append((round(s["lon"], 3), round(s["lat"], 3)))
            r["risk"].append(float(s["risk"]))
            r["t"].append(sim_min)
            r["peak_risk"] = max(r["peak_risk"], float(s["risk"]))
            r["peak"] = np.maximum(r["peak"], s["peak_targets"])

            k = min(len(r["risk"]) - 1, 5)
            slope = (r["risk"][-1] - r["risk"][-1 - k]) / (r["t"][-1] - r["t"][-1 - k]) if k >= 1 else 0.0
            age = sim_min - r["born"]
            if age < 8:
                stage = "initiating"
            elif slope * 10 > 0.03:
                stage = "intensifying"
            elif slope * 10 < -0.03:
                stage = "weakening"
            else:
                stage = "mature"
            eol, basis = None, "typical"
            if stage == "weakening" and slope < 0:
                eol, basis = min(max(0.0, (s["risk"] - 0.5) / -slope), 360.0), "trend"
            s["twin"] = {
                "stage": stage, "observed_min": round(age, 0), "trend_per_10min": round(slope * 10, 3),
                "eol_min": None if eol is None else round(eol, 0), "eol_basis": basis,
                "track_past": [list(p) for p in list(r["track"])[-40:]],
                "risk_hist": [round(x, 2) for x in list(r["risk"])[-40:]],
                "peak_risk": round(r["peak_risk"], 2),
                "peak_targets": [round(float(x), 1) for x in r["peak"]],
                "track_future": project_track(grid, u, v, s),
            }
        for sid in [k for k in self.rec if k not in alive]:
            r = self.rec.pop(sid)
            if r["t"][-1] - r["born"] < 10:      # one-frame flicker at the detection threshold, not a storm
                continue
            self.ended.appendleft({"id": sid, "lifetime_min": round(r["t"][-1] - r["born"], 0),
                                   "peak_risk": round(r["peak_risk"], 2), "t_end": r["t"][-1]})

    def ended_payload(self, sim_min: float) -> list[dict]:
        return [{"id": e["id"], "lifetime_min": e["lifetime_min"], "peak_risk": e["peak_risk"],
                 "ended_min_ago": round(sim_min - e["t_end"], 0)} for e in self.ended]