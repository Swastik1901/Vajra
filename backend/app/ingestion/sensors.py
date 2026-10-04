"""Turns the clean simulated field into what real sensors would deliver: separate sources with
different cadences, partial coverage, noise episodes and outages. Faults start at random
(FAULT_RATE) or on demand via POST /api/faults, so the fusion layer has something real to handle."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..core.config import FEATURES, SIGMA, SOURCES

KM_PER_DEG = 111.32
RANDOM_MODES = {"radar": ["partial", "noisy", "outage"], "satellite": ["noisy", "outage"],
                "lightning": ["outage", "noisy"], "environment": ["noisy"]}
STATUS = {"outage": "outage", "partial": "partial outage", "noisy": "noisy"}


@dataclass
class Fault:
    mode: str                      # outage | partial | noisy
    remaining: int
    mult: float = 1.0              # noise multiplier for "noisy"
    center: tuple[float, float] | None = None   # (lat, lon) of the blind spot for "partial"
    radius_km: float = 0.0


@dataclass
class Observation:
    values: np.ndarray             # (N, F) float32, NaN = nothing received
    mult: np.ndarray               # (N, F) noise multiplier (1 = nominal)
    health: list[dict]


class SensorSuite:
    def __init__(self, bbox, tick_minutes: float, fault_rate: float, seed: int):
        self.bbox = bbox
        self.tick_minutes = tick_minutes
        self.fault_rate = fault_rate
        self.rng = np.random.default_rng(seed + 7)
        self.faults: dict[str, Fault] = {}
        self.calls = 0
        self.last_avail = {s: 100.0 for s in SOURCES}

    # -------------------------------------------------------------- fault control
    def _new_fault(self, mode: str, duration: int) -> Fault:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        r = self.rng
        return Fault(mode, duration, mult=float(r.uniform(2.5, 5.0)),
                     center=(float(min_lat + (0.25 + 0.5 * r.random()) * (max_lat - min_lat)),
                             float(min_lon + (0.25 + 0.5 * r.random()) * (max_lon - min_lon))),
                     radius_km=float(r.uniform(22, 32)))

    def inject(self, source: str, mode: str, duration_ticks: int) -> None:
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}; use one of {list(SOURCES)}")
        if mode not in STATUS:
            raise ValueError(f"unknown mode {mode!r}; use one of {list(STATUS)}")
        self.faults[source] = self._new_fault(mode, int(duration_ticks))

    def clear(self) -> None:
        self.faults.clear()

    def _maybe_start_random(self) -> None:
        if self.fault_rate <= 0:
            return
        for src in SOURCES:
            if src not in self.faults and self.rng.random() < self.fault_rate:
                mode = str(self.rng.choice(RANDOM_MODES[src]))
                self.faults[src] = self._new_fault(mode, int(self.rng.integers(12, 31)))

    # -------------------------------------------------------------- observation operator
    def observe(self, tick: int, raw: dict[str, np.ndarray], lat: np.ndarray, lon: np.ndarray) -> Observation:
        n = len(lat)
        vals = np.stack([raw[f] for f in FEATURES], axis=1).astype(np.float32)
        mult = np.ones((n, len(FEATURES)), dtype=np.float32)
        first = self.calls == 0
        self.calls += 1
        self._maybe_start_random()
        health = []
        for src, spec in SOURCES.items():
            cols = [FEATURES.index(f) for f in spec["features"]]
            fault = self.faults.get(src)
            deliver = first or tick % spec["cadence"] == 0     # sources report at their own cadence
            avail, noise = self.last_avail[src], 1.0
            if not deliver:
                vals[:, cols] = np.nan                         # no new frame this tick (normal, not a fault)
            elif fault and fault.mode == "outage":
                vals[:, cols] = np.nan
                avail = 0.0
            elif fault and fault.mode == "partial":
                clat, clon = fault.center  # type: ignore[misc]
                dy = (lat - clat) * KM_PER_DEG
                dx = (lon - clon) * KM_PER_DEG * np.cos(np.radians(lat))
                hole = np.hypot(dx, dy) <= fault.radius_km
                vals[np.ix_(hole, cols)] = np.nan
                avail = 100.0 * (1.0 - float(hole.mean()))
            elif fault and fault.mode == "noisy":
                noise = fault.mult
                mult[:, cols] = noise
                for c in cols:
                    vals[:, c] += self.rng.normal(0, SIGMA[FEATURES[c]] * math.sqrt(noise ** 2 - 1), n)
                avail = 100.0
            elif deliver:
                avail = 100.0
            if deliver:
                self.last_avail[src] = avail
            health.append({
                "source": src, "label": spec["label"], "features": spec["features"],
                "status": STATUS[fault.mode] if fault else "ok",
                "mode": fault.mode if fault else None,
                "remaining_ticks": fault.remaining if fault else 0,
                "availability_pct": round(avail, 0), "noise_mult": round(noise, 1),
                "cadence_min": spec["cadence"] * self.tick_minutes,
            })
        for src in list(self.faults):
            self.faults[src].remaining -= 1
            if self.faults[src].remaining <= 0:
                del self.faults[src]
        return Observation(vals, mult, health)