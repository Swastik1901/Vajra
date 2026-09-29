"""NowcastEngine: ingest -> fuse/tile -> chunked inference -> track -> (advect) -> serialise -> broadcast."""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from ..core.config import FEATURES, HORIZONS_MIN, PLACES, TARGETS, Settings
from ..fusion.grid import HexGrid
from ..ingestion.simulator import StormSimulator
from ..models.registry import load_model
from .advection import forecast_targets
from .scoring import composite_risk
from .tracking import StormTracker, compute_etas, detect_storms


@dataclass
class TickState:
    tick: int
    sim_time: datetime
    raw: np.ndarray        # (N, F)
    targets: np.ndarray    # (N, 4)
    risk: np.ndarray       # (N,)
    u: np.ndarray
    v: np.ndarray
    storms: list[dict]
    etas: list[dict]
    inference_ms: float


class NowcastEngine:
    def __init__(self, s: Settings):
        self.s = s
        self.grid = HexGrid(s.bbox, s.h3_res, s.chunk_res)
        self.source = StormSimulator(s.bbox, seed=s.seed)   # <- swap for a real RawSource
        self.model = load_model(s.model_path)
        self.tracker = StormTracker()
        self.pool = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4))
        self.overlay = np.full((self.grid.n, len(FEATURES)), np.nan, dtype=np.float32)
        self.overlay_exp = np.zeros(self.grid.n, dtype=np.int64)
        self._lock = threading.Lock()
        self.tick_id = 0
        self.state: TickState | None = None
        self._cache: dict[tuple[int, int], str] = {}
        self._subs: set[asyncio.Queue] = set()
        self.grid_geojson = self.grid.to_geojson()

    # ----------------------------------------------------------- ingestion endpoint support
    def ingest(self, observations: list[dict], ttl_ticks: int) -> int:
        """Overlay point observations (e.g. a real gauge/radar pixel) onto the simulated field."""
        lat = np.array([o["lat"] for o in observations])
        lon = np.array([o["lon"] for o in observations])
        idx = self.grid.lookup(lat, lon)
        applied = 0
        with self._lock:
            for o, i in zip(observations, idx):
                if i < 0:
                    continue
                for k, val in o["values"].items():
                    self.overlay[i, FEATURES.index(k)] = val
                self.overlay_exp[i] = self.tick_id + ttl_ticks
                applied += 1
        return applied

    # ----------------------------------------------------------- one pipeline tick
    def compute_tick(self) -> None:
        g = self.grid
        self.tick_id += 1
        self.source.step(self.s.sim_minutes_per_tick)
        raw = self.source.sample(g.lat, g.lon)
        x = np.stack([raw[k] for k in FEATURES], axis=1).astype(np.float32)

        with self._lock:
            active = self.overlay_exp >= self.tick_id
            self.overlay[~active] = np.nan
            x = np.where(active[:, None] & ~np.isnan(self.overlay), self.overlay, x).astype(np.float32)

        # chunked (hierarchical) inference -> one work unit per parent hex
        t0 = time.perf_counter()
        chunks = list(g.chunks.values())
        parts = list(self.pool.map(lambda ch: (ch, self.model.predict(x[ch])), chunks))
        y = np.zeros((g.n, len(TARGETS)), dtype=np.float32)
        for ch, yp in parts:
            y[ch] = yp
        inference_ms = (time.perf_counter() - t0) * 1000

        risk = composite_risk(y)
        u, v = x[:, FEATURES.index("wind_u")], x[:, FEATURES.index("wind_v")]
        storms = self.tracker.update(detect_storms(g, risk, y, u, v))
        etas = compute_etas(storms)

        self.state = TickState(self.tick_id, self.source.sim_time, x, y, risk, u, v, storms, etas, inference_ms)
        self._cache = {}

    # ----------------------------------------------------------- serialisation
    def _forecast(self, horizon: int):
        st = self.state
        assert st is not None
        if horizon <= 0:
            return st.targets, st.risk
        y = forecast_targets(self.grid, st.targets, st.u, st.v, horizon)
        return y, composite_risk(y)

    def frame_json(self, horizon: int) -> str:
        st = self.state
        assert st is not None
        key = (st.tick, horizon)
        hit = self._cache.get(key)
        if hit:
            return hit
        y, risk = self._forecast(horizon)
        yr, rr = np.round(y, 1).tolist(), np.round(risk, 3).tolist()
        wr = np.round(np.stack([st.u, st.v], 1), 1).tolist()
        xr = np.round(st.raw, 1).tolist()
        cells = [{"r": r, "t": t, "w": w, "x": x} for r, t, w, x in zip(rr, yr, wr, xr)]
        payload = {
            "type": "frame",
            "tick": st.tick,
            "sim_time": st.sim_time.isoformat(),
            "horizon": horizon,
            "model": {"name": self.model.name, "version": self.model.version},
            "inference_ms": round(st.inference_ms, 1),
            "n_chunks": len(self.grid.chunks),
            "stats": {
                "n_cells": self.grid.n,
                "high_cells": int((risk >= 0.6).sum()),
                "mean_risk": round(float(risk.mean()), 3),
                "max": [round(float(v), 1) for v in y.max(axis=0)],
            },
            "storms": [{**s, **{k: round(s[k], 3) for k in ("lat", "lon", "radius_km", "risk", "u", "v",
                                                            "speed_kmh", "bearing_deg")}} for s in st.storms],
            "etas": st.etas,
            "cells": cells,
        }
        out = json.dumps(payload, separators=(",", ":"))
        self._cache[key] = out
        return out

    def snapshot_geojson(self, horizon: int) -> dict:
        """REST/polling payload: hex polygons + risk scores + wind vectors."""
        st = self.state
        assert st is not None
        y, risk = self._forecast(horizon)
        feats = []
        for i, f in enumerate(self.grid_geojson["features"]):
            u, v = float(st.u[i]), float(st.v[i])
            feats.append({
                "type": "Feature", "id": i, "geometry": f["geometry"],
                "properties": {
                    "id": f["properties"]["id"], "risk": round(float(risk[i]), 3),
                    **{TARGETS[k]["key"]: round(float(y[i, k]), 1) for k in range(len(TARGETS))},
                    "wind_u": round(u, 1), "wind_v": round(v, 1),
                    "wind_speed_ms": round(math.hypot(u, v), 1),
                    "wind_dir_deg": round((math.degrees(math.atan2(u, v)) + 360) % 360, 0),
                },
            })
        return {"type": "FeatureCollection", "tick": st.tick, "sim_time": st.sim_time.isoformat(),
                "horizon": horizon, "features": feats}

    def config_payload(self) -> dict:
        s, g = self.s, self.grid
        return {
            "bbox": list(s.bbox), "h3_res": s.h3_res, "chunk_res": s.chunk_res, "n_cells": g.n,
            "n_chunks": len(g.chunks), "cell_spacing_deg": g.spacing_deg, "features": FEATURES,
            "targets": TARGETS, "places": PLACES, "horizons": HORIZONS_MIN,
            "tick_seconds": s.tick_seconds, "sim_minutes_per_tick": s.sim_minutes_per_tick,
            "time_lapse": s.time_lapse, "model": {"name": self.model.name, "version": self.model.version},
        }

    # ----------------------------------------------------------- pub/sub + loop
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @staticmethod
    def notify(q: asyncio.Queue, tick: int) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(tick)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.s.tick_seconds)
            await asyncio.to_thread(self.compute_tick)
            for q in list(self._subs):
                self.notify(q, self.tick_id)
