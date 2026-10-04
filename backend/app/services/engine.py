"""NowcastEngine: ingest -> fuse/tile -> chunked inference -> track -> (advect) -> serialise -> broadcast.

The monitored region is swappable at runtime (`switch_region`). Everything a reader needs (grid, places,
values) hangs off ONE immutable `TickState`, so a region switch can never mix old and new arrays.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from ..core.cities import cities_in_bbox, in_india, nearest_city, region_name
from ..core.config import FEATURES, HORIZONS_MIN, REGION_SPAN, SOURCES, TARGETS, ZONES, Settings
from ..fusion.grid import HexGrid
from ..fusion.reliability import PROV_NAMES, FusionEngine, quality_from
from ..ingestion.sensors import SensorSuite
from ..ingestion.simulator import StormSimulator
from ..models.registry import load_model
from .ensemble import EnsStats, ensemble_stats, input_ensemble
from .explain import explain, region_stats
from .lead_time import blend_forecast, strategy_weights
from .scoring import composite_risk, zone_index
from .tracking import StormTracker, compute_etas, detect_storms
from .twin import TwinRegistry

POINT_HORIZONS = [0, 30, 60, 90, 120, 180, 240, 300, 360]


@dataclass
class Region:
    id: int
    name: str
    bbox: tuple[float, float, float, float]
    grid: HexGrid
    geojson: dict
    places: list[dict]


@dataclass
class TickState:
    tick: int
    sim_time: datetime
    region: Region
    raw: np.ndarray        # (N, F)
    targets: np.ndarray    # (N, 4)
    risk: np.ndarray       # (N,)
    u: np.ndarray
    v: np.ndarray
    storms: list[dict]
    etas: list[dict]
    inference_ms: float
    rel: np.ndarray        # (N, F) reliability of each fused input
    prov: np.ndarray       # (N, F) provenance code
    quality: np.ndarray    # (N,) overall data quality
    ens0: np.ndarray       # (K, N, 4) input-perturbed ensemble
    ens_stats0: EnsStats
    sensors: list[dict]
    fusion: dict
    ended: list[dict]


def region_bbox(lat: float, lon: float) -> tuple[float, float, float, float]:
    dlon, dlat = REGION_SPAN[0] / 2, REGION_SPAN[1] / 2
    return (round(lon - dlon, 3), round(lat - dlat, 3), round(lon + dlon, 3), round(lat + dlat, 3))


class NowcastEngine:
    def __init__(self, s: Settings):
        self.s = s
        self.model = load_model(s.model_path)
        self.pool = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4))
        self._rlock = threading.RLock()   # serialises ticks and region swaps
        self._lock = threading.Lock()     # overlay (ingest) access
        self.tick_id = 0
        self._region_counter = 0
        self.state: TickState | None = None
        self._cache: dict[tuple[int, int], str] = {}
        self._fc: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
        self._ec: dict[tuple[int, int], EnsStats] = {}
        self._subs: set[asyncio.Queue] = set()
        self._install_region(self._build_region(s.bbox))

    # ------------------------------------------------------------ regions
    def _build_region(self, bbox: tuple[float, float, float, float]) -> Region:
        grid = HexGrid(bbox, self.s.h3_res, self.s.chunk_res)      # heavy: done outside the lock
        self._region_counter += 1
        return Region(self._region_counter, region_name((bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2),
                      bbox, grid, grid.to_geojson(), cities_in_bbox(bbox))

    def _install_region(self, region: Region) -> None:
        self.region = region
        self.source = StormSimulator(region.bbox, seed=self.s.seed + region.id)   # <- swap for a real RawSource
        self.tracker = StormTracker()
        n = region.grid.n
        self.overlay = np.full((n, len(FEATURES)), np.nan, dtype=np.float32)
        self.overlay_exp = np.zeros(n, dtype=np.int64)
        self.history: deque[TickState] = deque(maxlen=self.s.explain_lag_ticks + 1)
        self.storm_hist: dict[int, deque] = {}
        self.sensors = SensorSuite(region.bbox, self.s.sim_minutes_per_tick, self.s.fault_rate, self.s.seed + region.id)
        self.fusion = FusionEngine(n)
        self.twins = TwinRegistry()
        self._t0 = self.source.sim_time

    def switch_region(self, lat: float, lon: float) -> int:
        """Re-centre the monitored box on (lat, lon). Blocking; call via a thread."""
        region = self._build_region(region_bbox(lat, lon))
        with self._rlock:
            self._install_region(region)
            self._compute()
        return region.id

    @property
    def grid(self) -> HexGrid:
        assert self.state is not None
        return self.state.region.grid

    @property
    def grid_geojson(self) -> dict:
        assert self.state is not None
        r = self.state.region
        return {**r.geojson, "region_id": r.id}

    # ------------------------------------------------------------ ingestion endpoint support
    def ingest(self, observations: list[dict], ttl_ticks: int) -> int:
        """Overlay point observations (e.g. a real gauge/radar pixel) onto the simulated field."""
        with self._rlock:
            lat = np.array([o["lat"] for o in observations])
            lon = np.array([o["lon"] for o in observations])
            idx = self.region.grid.lookup(lat, lon)
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

    # ------------------------------------------------------------ one pipeline tick
    def compute_tick(self) -> None:
        with self._rlock:
            self._compute()

    def _compute(self) -> None:
        region = self.region
        g = region.grid
        self.tick_id += 1
        self.source.step(self.s.sim_minutes_per_tick)
        raw = self.source.sample(g.lat, g.lon)
        obs = self.sensors.observe(self.tick_id, raw, g.lat, g.lon)      # what the sensors actually deliver
        fr = self.fusion.fuse(obs, g)                                    # gap-free values + reliability
        x, rel, prov = fr.values.astype(np.float32), fr.reliability.copy(), fr.provenance.copy()

        with self._lock:
            active = self.overlay_exp >= self.tick_id
            self.overlay[~active] = np.nan
            ov = active[:, None] & ~np.isnan(self.overlay)
            x = np.where(ov, self.overlay, x).astype(np.float32)
            rel = np.where(ov, 1.0, rel).astype(np.float32)
            prov = np.where(ov, 0, prov).astype(np.int8)
        quality = quality_from(rel).astype(np.float32)

        # chunked (hierarchical) inference -> one work unit per parent hex
        t0 = time.perf_counter()
        parts = list(self.pool.map(lambda ch: (ch, self.model.predict(x[ch])), list(g.chunks.values())))
        y = np.zeros((g.n, len(TARGETS)), dtype=np.float32)
        for ch, yp in parts:
            y[ch] = yp
        inference_ms = (time.perf_counter() - t0) * 1000

        ens0 = input_ensemble(self.model, x, rel, self.pool, self.s.n_members, np.random.default_rng(self.tick_id))

        risk = composite_risk(y)
        u, v = x[:, FEATURES.index("wind_u")], x[:, FEATURES.index("wind_v")]
        sim_min = (self.source.sim_time - self._t0).total_seconds() / 60.0
        storms = self.tracker.update(detect_storms(g, risk, y, u, v))
        self.twins.update(storms, g, u, v, sim_min)                      # digital twins: track, stage, projected path
        etas = compute_etas(storms, region.places)
        ens_stats0 = ensemble_stats(g, y, y, ens0, u, v, 0, self.tick_id * 1000)
        for st_ in storms:
            pk = st_["peak_idx"]
            st_["lo"], st_["hi"] = float(ens_stats0.lo[pk]), float(ens_stats0.hi[pk])
            st_["conf"], st_["p_warning"] = float(ens_stats0.conf[pk]), float(ens_stats0.p[pk])

        # explainability: compare each storm's footprint now vs ~lag ticks ago
        lag = self.s.explain_lag_ticks
        for st_ in storms:
            stats = region_stats(st_["members"], x, y, risk)
            h = self.storm_hist.setdefault(st_["id"], deque(maxlen=lag + 1))
            h.append(stats)
            st_["why"] = explain(stats, h[0] if len(h) > 1 else None, (len(h) - 1) * self.s.sim_minutes_per_tick)
        alive = {st_["id"] for st_ in storms}
        for sid in [k for k in self.storm_hist if k not in alive]:
            del self.storm_hist[sid]

        state = TickState(self.tick_id, self.source.sim_time, region, x, y, risk, u, v, storms, etas, inference_ms,
                          rel, prov, quality, ens0, ens_stats0, obs.health, fr.summary,
                          self.twins.ended_payload(sim_min))
        self.history.append(state)
        self._cache, self._fc, self._ec = {}, {}, {}
        self.state = state          # single atomic publish

    # ------------------------------------------------------------ serialisation
    def _forecast(self, st: TickState, horizon: int):
        key = (st.tick, horizon)
        hit = self._fc.get(key)
        if hit is not None:
            return hit
        y = st.targets if horizon <= 0 else blend_forecast(st.region.grid, st, horizon)
        out = (y, st.risk if horizon <= 0 else composite_risk(y))
        self._fc[key] = out
        return out

    def _ens(self, st: TickState, horizon: int) -> EnsStats:
        key = (st.tick, horizon)
        hit = self._ec.get(key)
        if hit is not None:
            return hit
        if horizon <= 0:
            out = st.ens_stats0
        else:
            y, _ = self._forecast(st, horizon)
            out = ensemble_stats(st.region.grid, y, st.targets, st.ens0, st.u, st.v, horizon, st.tick * 1000 + horizon)
        self._ec[key] = out
        return out

    def frame_json(self, horizon: int) -> str:
        st = self.state
        assert st is not None
        key = (st.tick, horizon)
        hit = self._cache.get(key)
        if hit:
            return hit
        g = st.region.grid
        y, risk = self._forecast(st, horizon)
        ens = self._ens(st, horizon)
        yr, rr = np.round(y, 1).tolist(), np.round(risk, 3).tolist()
        wr = np.round(np.stack([st.u, st.v], 1), 1).tolist()
        xr = np.round(st.raw, 1).tolist()
        lo, hi = np.round(ens.lo, 2).tolist(), np.round(ens.hi, 2).tolist()
        cf, pw, qq = np.round(ens.conf, 2).tolist(), np.round(ens.p, 2).tolist(), np.round(st.quality, 2).tolist()
        cells = [{"r": r, "t": t, "w": w, "x": x, "lo": a, "hi": b, "c": c, "p": p, "q": q}
                 for r, t, w, x, a, b, c, p, q in zip(rr, yr, wr, xr, lo, hi, cf, pw, qq)]
        payload = {
            "type": "frame",
            "tick": st.tick,
            "region_id": st.region.id,
            "region_name": st.region.name,
            "sim_time": st.sim_time.isoformat(),
            "horizon": horizon,
            "model": {"name": self.model.name, "version": self.model.version},
            "inference_ms": round(st.inference_ms, 1),
            "n_chunks": len(g.chunks),
            "stats": {
                "n_cells": g.n,
                "high_cells": int((risk >= 0.6).sum()),
                "mean_risk": round(float(risk.mean()), 3),
                "max": [round(float(v), 1) for v in y.max(axis=0)],
            },
            "storms": [self._public_storm(s) for s in st.storms],
            "etas": st.etas,
            "strategy": {"horizon": horizon, "weights": {k: round(w, 3) for k, w in strategy_weights(horizon).items()}},
            "sensors": st.sensors,
            "fusion": st.fusion,
            "twins_ended": st.ended,
            "cells": cells,
        }
        out = json.dumps(payload, separators=(",", ":"))
        self._cache[key] = out
        return out

    def snapshot_geojson(self, horizon: int) -> dict:
        """REST/polling payload: hex polygons + risk scores + wind vectors."""
        st = self.state
        assert st is not None
        y, risk = self._forecast(st, horizon)
        ens = self._ens(st, horizon)
        zi = zone_index(risk)
        feats = []
        for i, f in enumerate(st.region.geojson["features"]):
            u, v = float(st.u[i]), float(st.v[i])
            feats.append({
                "type": "Feature", "id": i, "geometry": f["geometry"],
                "properties": {
                    "id": f["properties"]["id"], "risk": round(float(risk[i]), 3),
                    "zone": ZONES[int(zi[i])]["key"],
                    "risk_lo": round(float(ens.lo[i]), 2), "risk_hi": round(float(ens.hi[i]), 2),
                    "confidence": round(float(ens.conf[i]), 2), "data_quality": round(float(st.quality[i]), 2),
                    **{TARGETS[k]["key"]: round(float(y[i, k]), 1) for k in range(len(TARGETS))},
                    "wind_u": round(u, 1), "wind_v": round(v, 1),
                    "wind_speed_ms": round(math.hypot(u, v), 1),
                    "wind_dir_deg": round((math.degrees(math.atan2(u, v)) + 360) % 360, 0),
                },
            })
        return {"type": "FeatureCollection", "tick": st.tick, "region_id": st.region.id,
                "sim_time": st.sim_time.isoformat(), "horizon": horizon, "features": feats}

    def config_payload(self) -> dict:
        s = self.s
        st = self.state
        assert st is not None
        r, g = st.region, st.region.grid
        return {
            "bbox": list(r.bbox), "region_id": r.id, "region_name": r.name,
            "h3_res": s.h3_res, "chunk_res": s.chunk_res, "n_cells": g.n,
            "n_chunks": len(g.chunks), "cell_spacing_deg": g.spacing_deg, "features": FEATURES,
            "targets": TARGETS, "places": r.places, "horizons": HORIZONS_MIN,
            "tick_seconds": s.tick_seconds, "sim_minutes_per_tick": s.sim_minutes_per_tick,
            "time_lapse": s.time_lapse, "zones": ZONES, "cell_area_km2": round(g.cell_area_km2, 2),
            "explain_lag_min": s.explain_lag_ticks * s.sim_minutes_per_tick, "n_members": s.n_members,
            "sources": SOURCES,
            "model": {"name": self.model.name, "version": self.model.version},
        }

    @staticmethod
    def _public_storm(s: dict) -> dict:
        out = {k: v for k, v in s.items() if k not in ("members", "peak_idx")}
        for k in ("lat", "lon", "radius_km", "risk", "u", "v", "speed_kmh", "bearing_deg", "lo", "hi", "conf", "p_warning"):
            out[k] = round(out[k], 3)
        return out

    # ------------------------------------------------------------ sensor faults (demo / testing)
    def inject_fault(self, source: str, mode: str, duration_ticks: int) -> None:
        with self._rlock:
            self.sensors.inject(source, mode, duration_ticks)

    def clear_faults(self) -> None:
        with self._rlock:
            self.sensors.clear()

    def sensors_payload(self) -> dict:
        st = self.state
        assert st is not None
        return {"sources": st.sensors, "fusion": st.fusion}

    # ------------------------------------------------------------ click-a-point APIs
    def point_info(self, lat: float, lon: float) -> dict:
        """Everything the dashboard shows when the user clicks a spot on the map."""
        st = self.state
        assert st is not None
        g = st.region.grid
        idx = int(g.lookup(np.array([lat]), np.array([lon]))[0])
        info = {
            "lat": lat, "lon": lon, "in_india": in_india(lat, lon), "in_domain": idx >= 0,
            "region_id": st.region.id, "region_name": st.region.name,
            "nearest": nearest_city(lat, lon), "cell": idx if idx >= 0 else None,
            "now": None, "forecast": [], "arrivals": [],
        }
        if idx >= 0:
            for m in POINT_HORIZONS:
                y, r = self._forecast(st, m)
                e = self._ens(st, m)
                info["forecast"].append({"minutes": m, "risk": round(float(r[idx]), 3),
                                         "lo": round(float(e.lo[idx]), 2), "hi": round(float(e.hi[idx]), 2),
                                         "conf": round(float(e.conf[idx]), 2), "p_warning": round(float(e.p[idx]), 2),
                                         "targets": [round(float(v), 1) for v in y[idx]]})
            info["quality"] = {
                "score": round(float(st.quality[idx]), 2),
                "features": [{"name": f, "value": round(float(st.raw[idx, j]), 1),
                              "reliability": round(float(st.rel[idx, j]), 2), "source": PROV_NAMES[int(st.prov[idx, j])]}
                             for j, f in enumerate(FEATURES)],
            }
            info["now"] = {**info["forecast"][0], "wind": [round(float(st.u[idx]), 1), round(float(st.v[idx]), 1)]}
            info["arrivals"] = compute_etas(st.storms, [{"name": "this point", "lat": lat, "lon": lon}])
        return info

    def explain_cell(self, i: int) -> dict:
        """Why is risk changing in this one cell? (observed change over the explain window)"""
        hist = list(self.history)
        st = hist[-1]
        now = region_stats(np.array([i]), st.raw, st.targets, st.risk, single=True)
        if len(hist) < 2:
            return explain(now, None, 0.0)
        old = hist[0]
        before = region_stats(np.array([i]), old.raw, old.targets, old.risk, single=True)
        return explain(now, before, (len(hist) - 1) * self.s.sim_minutes_per_tick)

    # ------------------------------------------------------------ pub/sub + loop
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

    def broadcast(self) -> None:
        for q in list(self._subs):
            self.notify(q, self.tick_id)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.s.tick_seconds)
            await asyncio.to_thread(self.compute_tick)
            self.broadcast()