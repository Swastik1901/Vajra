"""Storm-cell detection (connected components on the hex graph), ID tracking, and ETA to places."""
from __future__ import annotations

import math

import numpy as np

from ..core.config import PLACES, TARGETS
from ..fusion.grid import HexGrid
from .scoring import dominant_hazard

KM_PER_DEG = 111.32


def detect_storms(grid: HexGrid, risk: np.ndarray, y: np.ndarray, u: np.ndarray, v: np.ndarray,
                  thr: float = 0.5, min_cells: int = 2) -> list[dict]:
    mask = risk >= thr
    seen = np.zeros(grid.n, dtype=bool)
    out: list[dict] = []
    for s in np.flatnonzero(mask):
        if seen[s]:
            continue
        stack, members = [int(s)], []
        seen[s] = True
        while stack:
            c = stack.pop()
            members.append(c)
            for nb in grid.nbr[c]:
                if nb >= 0 and mask[nb] and not seen[nb]:
                    seen[nb] = True
                    stack.append(int(nb))
        if len(members) < min_cells:
            continue
        m = np.asarray(members)
        w = risk[m]
        ws = w.sum()
        peak = m[int(np.argmax(risk[m]))]
        uu, vv = float((u[m] * w).sum() / ws), float((v[m] * w).sum() / ws)
        speed = math.hypot(uu, vv)
        out.append({
            "lat": float((grid.lat[m] * w).sum() / ws),
            "lon": float((grid.lon[m] * w).sum() / ws),
            "radius_km": float(math.sqrt(len(m) * grid.cell_area_km2 / math.pi)),
            "risk": float(risk[m].max()),
            "u": uu, "v": vv,
            "speed_kmh": speed * 3.6,
            "bearing_deg": (math.degrees(math.atan2(uu, vv)) + 360) % 360,
            "hazard": dominant_hazard(y[peak]),
            "n_cells": len(m),
        })
    return out


class StormTracker:
    """Greedy nearest-centroid association to keep stable storm IDs between ticks."""

    def __init__(self, max_dist_km: float = 40.0):
        self.prev: list[dict] = []
        self.next_id = 1
        self.max_dist = max_dist_km

    def update(self, dets: list[dict]) -> list[dict]:
        used: set[int] = set()
        for d in sorted(dets, key=lambda d: -d["risk"]):
            best, best_d = None, self.max_dist
            for p in self.prev:
                if p["id"] in used:
                    continue
                dx = (d["lon"] - p["lon"]) * KM_PER_DEG * math.cos(math.radians(d["lat"]))
                dy = (d["lat"] - p["lat"]) * KM_PER_DEG
                dist = math.hypot(dx, dy)
                if dist < best_d:
                    best, best_d = p, dist
            if best is not None:
                d["id"] = best["id"]; used.add(best["id"])
            else:
                d["id"] = self.next_id; self.next_id += 1
        self.prev = dets
        return dets


def compute_etas(storms: list[dict], max_minutes: float = 360.0) -> list[dict]:
    """Earliest arrival of each storm's (advecting) footprint at each place."""
    best: dict[str, dict] = {}
    for st in storms:
        sp = math.hypot(st["u"], st["v"])
        coslat = math.cos(math.radians(st["lat"]))
        for p in PLACES:
            dx = (p["lon"] - st["lon"]) * KM_PER_DEG * coslat
            dy = (p["lat"] - st["lat"]) * KM_PER_DEG
            eta = None
            if math.hypot(dx, dy) <= st["radius_km"]:
                eta = 0.0
            elif sp > 1.0:
                vx, vy = st["u"] / sp, st["v"] / sp
                along = dx * vx + dy * vy
                cross = abs(dx * vy - dy * vx)
                if along > 0 and cross <= st["radius_km"] + 8:
                    eta = (along * 1000.0 / sp) / 60.0
            if eta is not None and eta <= max_minutes:
                cur = best.get(p["name"])
                if cur is None or eta < cur["eta_min"]:
                    best[p["name"]] = {"place": p["name"], "storm_id": st["id"], "eta_min": round(eta, 1),
                                       "hazard": st["hazard"], "risk": round(st["risk"], 2)}
    return sorted(best.values(), key=lambda e: e["eta_min"])
