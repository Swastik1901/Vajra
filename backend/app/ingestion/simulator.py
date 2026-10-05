"""Physically-flavoured storm simulator that streams raw per-cell observations.

Storms are Gaussian reflectivity cores that spawn upstream (NW), mature, decay, and drift with a
spatially/temporally varying steering wind (pre-monsoon nor'wester style). Each core generates a
consistent set of raw variables: reflectivity, VIL, cloud-top temp/cooling, CAPE, gust-front outflow,
lightning pulses, humidity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from ..core.config import FEATURES

KM_PER_DEG = 111.32


@dataclass
class Storm:
    id: int
    lat: float
    lon: float
    radius_km: float
    peak_dbz: float
    age: float   # minutes
    life: float  # minutes

    @property
    def phase(self) -> float:
        return math.pi * min(self.age / self.life, 1.0)

    @property
    def intensity(self) -> float:
        return math.sin(self.phase) ** 0.8

    @property
    def growth(self) -> float:
        return math.cos(self.phase)  # >0 growing, <0 decaying


class StormSimulator:
    def __init__(self, bbox: tuple[float, float, float, float], seed: int = 42, target_storms: int = 6,
                 noise_scale: float = 1.0):
        self.bbox = bbox
        self.ns = noise_scale      # 1 = normal; ~0.1 = calm demo (storms still move, numbers stop jittering)
        self.rng = np.random.default_rng(seed)
        self.cx = (bbox[0] + bbox[2]) / 2
        self.cy = (bbox[1] + bbox[3]) / 2
        self.target = target_storms
        self.t_min = 0.0
        self.start = datetime.now(timezone.utc).replace(microsecond=0)
        self.storms: list[Storm] = []
        self._next_id = 1
        for _ in range(target_storms):
            self._spawn(anywhere=True)

    @property
    def sim_time(self) -> datetime:
        return self.start + timedelta(minutes=self.t_min)

    # ---------------------------------------------------------------- dynamics
    def steering(self, lat, lon, t_min: float):
        ph = 2 * np.pi * t_min / 480.0
        u = 9.0 + 3.0 * np.sin(ph + (lon - self.cx) * 2.0)
        v = -4.0 + 3.0 * np.cos(ph + (lat - self.cy) * 2.0)
        return u, v

    def _spawn(self, anywhere: bool = False) -> None:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        r = self.rng
        life = float(r.uniform(150, 300))
        if anywhere:
            lat, lon, age = r.uniform(min_lat, max_lat), r.uniform(min_lon, max_lon), r.uniform(0, life * 0.6)
        else:
            lat, lon, age = r.uniform(min_lat + 0.3, max_lat), min_lon + r.uniform(0.0, 0.3), 0.0
        self.storms.append(Storm(self._next_id, float(lat), float(lon), float(r.uniform(8, 18)),
                                 float(r.uniform(48, 64)), float(age), life))
        self._next_id += 1

    def step(self, dt_min: float) -> None:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        for s in self.storms:
            u, v = self.steering(s.lat, s.lon, self.t_min)
            s.lat += float(v) * dt_min * 60 / (KM_PER_DEG * 1000)
            s.lon += float(u) * dt_min * 60 / (KM_PER_DEG * 1000 * math.cos(math.radians(s.lat)))
            s.age += dt_min
        self.t_min += dt_min
        m = 0.4
        self.storms = [s for s in self.storms
                       if s.age < s.life and min_lon - m < s.lon < max_lon + m and min_lat - m < s.lat < max_lat + m]
        while len(self.storms) < self.target and self.rng.random() < 0.35:
            self._spawn()

    # ---------------------------------------------------------------- observation operator
    def sample(self, lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]:
        n = len(lat)
        rng = self.rng
        dbz = np.full(n, 8.0)
        conv = np.zeros(n)
        cool = np.zeros(n)
        out_u = np.zeros(n)
        out_v = np.zeros(n)
        coslat = np.cos(np.radians(lat))
        for s in self.storms:
            dy = (lat - s.lat) * KM_PER_DEG
            dx = (lon - s.lon) * KM_PER_DEG * coslat
            d2 = dx * dx + dy * dy
            g = np.exp(-d2 / (2 * s.radius_km ** 2))
            inten = s.intensity
            dbz = np.maximum(dbz, s.peak_dbz * inten * g)
            conv = np.maximum(conv, inten * g)
            cool -= 12.0 * g * max(s.growth, 0.0)
            r = np.sqrt(d2) + 1e-3
            ring = np.exp(-((r - 0.9 * s.radius_km) ** 2) / (2 * (0.5 * s.radius_km) ** 2))
            mag = 14.0 * inten * ring  # gust-front outflow (m/s)
            out_u += mag * dx / r
            out_v += mag * dy / r

        dbz = np.clip(dbz + rng.normal(0, 1.0 * self.ns, n), 0, 70)
        u0, v0 = self.steering(lat, lon, self.t_min)
        vil = np.clip((dbz - 20) * 1.15, 0, None)
        lam = np.where(dbz > 35, 0.25 * np.clip(dbz - 35, 0, None) ** 1.3, 0.02)
        raw = {
            "dbz": dbz,
            "vil": vil,
            "cth_k": np.clip(288 - 1.7 * np.clip(dbz - 10, 0, None) - 6 * conv + rng.normal(0, 1.5 * self.ns, n), 190, 300),
            "cooling_k15": cool + rng.normal(0, 0.3 * self.ns, n),
            "cape": np.clip(600 + 2600 * conv + rng.normal(0, 80 * self.ns, n), 0, None),
            "wind_u": u0 + out_u + rng.normal(0, 0.3 * self.ns, n),
            "wind_v": v0 + out_v + rng.normal(0, 0.3 * self.ns, n),
            "lightning": (rng.poisson(lam) if self.ns >= 0.5 else np.round(lam)).astype(float),
            "humidity": np.clip(55 + 35 * conv + rng.normal(0, 2 * self.ns, n), 10, 100),
        }
        return {k: raw[k] for k in FEATURES}