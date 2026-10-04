"""Reliability-aware fusion: every cell/feature gets a value, a reliability (0..1) and a provenance.

Order of preference when a value is missing:
  short gap (<=3 ticks)  -> persistence of the last good value, decaying toward climatology
  longer gap             -> cross-sensor proxy (e.g. cloud-top temperature -> reflectivity)
                            -> neighbour fill (inpainting from valid neighbours)
                            -> decayed persistence -> climatological default
Noisy sources are down-weighted with a Kalman-style gain against the last good value.
The proxies encode relationships of the simulated atmosphere; for real data they must be re-fitted.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.config import BACKGROUND, FEATURE_WEIGHT, FEATURES, RANGES, SOURCES, TAU_TICKS
from ..ingestion.sensors import Observation
from .grid import HexGrid

PROV_NAMES = ["observed", "proxy", "persistence", "neighbour fill", "default"]
_I = {f: i for i, f in enumerate(FEATURES)}
_BG = np.array([BACKGROUND[f] for f in FEATURES], dtype=np.float64)
_TAU = np.array([TAU_TICKS[f] for f in FEATURES], dtype=np.float64)
_W = np.array([FEATURE_WEIGHT[f] for f in FEATURES], dtype=np.float64)
_CAD = np.array([next(s['cadence'] for s in SOURCES.values() if f in s['features']) for f in FEATURES], dtype=np.float64)
_LO = np.array([RANGES[f][0] for f in FEATURES], dtype=np.float64)
_HI = np.array([RANGES[f][1] for f in FEATURES], dtype=np.float64)


def quality_from(rel: np.ndarray) -> np.ndarray:
    """Overall data quality per cell: importance-weighted mean reliability."""
    return (rel * _W).sum(axis=1) / _W.sum()


@dataclass
class FusionResult:
    values: np.ndarray       # (N, F) gap-free
    reliability: np.ndarray  # (N, F) 0..1
    provenance: np.ndarray   # (N, F) index into PROV_NAMES
    quality: np.ndarray      # (N,)
    summary: dict


class FusionEngine:
    def __init__(self, n: int):
        f = len(FEATURES)
        self.last_obs = np.full((n, f), np.nan)     # last good (fused) observation per cell/feature
        self.age = np.full((n, f), 99, dtype=np.int64)  # ticks since it was observed
        self.last_rel = np.zeros((n, f))                # reliability of that observation

    def fuse(self, obs: Observation, grid: HexGrid) -> FusionResult:
        n, nf = obs.values.shape
        v = obs.values.astype(np.float64)
        m = obs.mult.astype(np.float64)
        valid = ~np.isnan(v)

        # 1) observed values; noisy ones are blended with the last good value
        prior = self.last_obs
        have = ~np.isnan(prior)
        p_var = 4.0 * (1 + np.minimum(self.age, 10))
        gain = np.where(m <= 1.2, 1.0, p_var / (p_var + m * m))
        out = np.where(valid, np.where(have, prior + gain * (v - prior), v), np.nan)
        rel = np.zeros((n, nf))
        prov = np.full((n, nf), 4, dtype=np.int8)
        prov[valid] = 0
        rel[valid] = np.clip(1.0 / m[valid], 0.1, 1.0)

        self.age = np.where(valid, 0, np.minimum(self.age + 1, 99))
        self.last_obs = np.where(valid, out, self.last_obs)
        self.last_rel = np.where(valid, rel, self.last_rel)   # held values inherit the quality of their source frame
        age = self.age.astype(np.float64)
        with np.errstate(invalid="ignore"):
            decayed = np.where(~np.isnan(self.last_obs), _BG + (self.last_obs - _BG) * np.exp(-age / _TAU), np.nan)

            # 2) short gaps: persistence
            missing = ~valid
            # a value held within its source's normal reporting interval is still the latest observation
            short = missing & (age <= np.maximum(3.0, _CAD - 1)) & ~np.isnan(decayed)
            eff = np.maximum(age - (_CAD - 1), 0.0)          # staleness beyond the normal cadence
            out[short] = decayed[short]
            prov[short] = np.where(eff == 0, 0, 2)[short]
            rel[short] = (self.last_rel * np.where(eff == 0, 0.98, 0.7 * np.exp(-eff / 6.0)))[short]
            todo = missing & ~short

            # 3) cross-sensor proxies (only from inputs observed this tick)
            def put(name: str, proxy: np.ndarray, cond: np.ndarray, r: float) -> None:
                j = _I[name]
                sel = cond & todo[:, j]
                out[sel, j] = proxy[sel]
                prov[sel, j] = 1
                rel[sel, j] = r
                todo[sel, j] = False

            cth = out[:, _I["cth_k"]]
            put("dbz", np.clip(np.where(cth < 282, 10 + (285 - cth) / 1.7, 8.0), 0, 70), prov[:, _I["cth_k"]] == 0, 0.5)
            dbz = out[:, _I["dbz"]]
            put("cth_k", np.clip(288 - 1.7 * np.clip(dbz - 10, 0, None) - 3, 190, 300), prov[:, _I["dbz"]] == 0, 0.5)
            dbz = out[:, _I["dbz"]]
            dbz_ok = prov[:, _I["dbz"]] <= 1
            put("vil", np.clip((dbz - 20) * 1.15, 0, None), dbz_ok, 0.45)
            put("lightning", np.where(dbz > 35, 0.25 * np.clip(dbz - 35, 0, None) ** 1.3, 0.02), dbz_ok, 0.4)

            # 4) neighbour fill (inpaint inwards from valid neighbours, 3 rings)
            for j in range(nf):
                rem = todo[:, j]
                src = prov[:, j] == 0
                if not rem.any() or not src.any():
                    continue
                for _ in range(3):
                    mean, cnt = grid.masked_neighbor_mean(np.nan_to_num(out[:, j]), src)
                    fill = rem & (cnt > 0)
                    if not fill.any():
                        break
                    out[fill, j] = mean[fill]
                    prov[fill, j] = 3
                    rel[fill, j] = (0.4 * np.exp(-age[:, j] / 10.0))[fill]
                    src = src | fill
                    rem = rem & ~fill
                todo[:, j] = rem

            # 5) whatever is left: decayed persistence, else climatological default
            dec_ok = ~np.isnan(decayed)
            sel = todo & dec_ok
            out[sel] = decayed[sel]
            prov[sel] = 2
            rel[sel] = np.maximum(0.1, 0.35 * np.exp(-age / 10.0))[sel]
            sel = todo & ~dec_ok
            out[sel] = np.broadcast_to(_BG, (n, nf))[sel]
            prov[sel] = 4
            rel[sel] = 0.1

        out = np.clip(out, _LO, _HI)
        q = quality_from(rel)
        counts = np.bincount(prov.ravel(), minlength=len(PROV_NAMES))
        summary = {"mean_quality": round(float(q.mean()), 3), "min_quality": round(float(q.min()), 3),
                   "mix": {PROV_NAMES[i]: round(100.0 * counts[i] / prov.size, 1) for i in range(len(PROV_NAMES))}}
        return FusionResult(out.astype(np.float32), rel.astype(np.float32), prov, q.astype(np.float32), summary)