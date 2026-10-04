"""Confidence-aware predictions: a small ensemble turns one number into risk + range + confidence.

* Input uncertainty: model inputs are perturbed in proportion to how UNRELIABLE they are
  (reliability from the fusion layer), so bad data widens the range.
* Lead-time uncertainty: members are shifted (position error grows with speed x lead time) and
  scaled (amplitude error grows with lead time).
The spreads are engineered, not calibrated against verification data. Calibrate before trusting them.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from ..core.config import ENS_SIGMA, FEATURES, RANGES
from ..fusion.grid import HexGrid
from .scoring import composite_risk, composite_risk_nd

_SIG = np.array([ENS_SIGMA[f] for f in FEATURES])
_LO = np.array([RANGES[f][0] for f in FEATURES], dtype=np.float32)
_HI = np.array([RANGES[f][1] for f in FEATURES], dtype=np.float32)
M_PER_DEG = 111_320.0


class EnsStats(NamedTuple):
    lo: np.ndarray    # (N,) 10th percentile of risk
    hi: np.ndarray    # (N,) 90th percentile of risk
    conf: np.ndarray  # (N,) 0..1, 1 = tight ensemble
    p: np.ndarray     # (N,) probability risk reaches the Warning zone (>= 0.5)


def input_ensemble(model, x: np.ndarray, rel: np.ndarray, pool, k: int, rng: np.random.Generator) -> np.ndarray:
    """(K, N, 4) model outputs for K perturbed copies of the inputs."""
    sig = _SIG[None, :] * (0.5 + 2.5 * (1.0 - rel))
    members = [np.clip(x + rng.normal(0, 1, x.shape) * sig, _LO, _HI).astype(np.float32) for _ in range(k)]
    return np.stack(list(pool.map(model.predict, members)), axis=0).astype(np.float32)


def member_forecast(grid: HexGrid, ctrl_t: np.ndarray, ctrl0: np.ndarray, ens0: np.ndarray,
                    u: np.ndarray, v: np.ndarray, minutes: float, rng: np.random.Generator) -> np.ndarray:
    k = ens0.shape[0]
    speed = float(np.hypot(u, v).mean())
    sigma_m = 800.0 + 0.06 * speed * minutes * 60.0     # ~6 % of the distance travelled
    dx, dy = rng.normal(0, sigma_m, k), rng.normal(0, sigma_m, k)
    amp = np.exp(rng.normal(0, 0.04 + 0.22 * minutes / 360.0, k))
    fade = np.exp(-minutes / 120.0)                      # input uncertainty fades as other errors take over
    coslat = np.cos(np.radians(grid.lat))
    out = np.empty_like(ens0)
    for i in range(k):
        if minutes > 0:
            idx = grid.lookup(grid.lat - dy[i] / M_PER_DEG, grid.lon - dx[i] / (M_PER_DEG * coslat))
            shifted = np.where((idx >= 0)[:, None], ctrl_t[np.maximum(idx, 0)], 0.0)
        else:
            shifted = ctrl_t
        out[i] = np.clip((shifted + (ens0[i] - ctrl0) * fade) * amp[i], 0, None)
    return out


def ensemble_stats(grid: HexGrid, ctrl_t: np.ndarray, ctrl0: np.ndarray, ens0: np.ndarray,
                   u: np.ndarray, v: np.ndarray, minutes: float, seed: int) -> EnsStats:
    members = member_forecast(grid, ctrl_t, ctrl0, ens0, u, v, minutes, np.random.default_rng(seed))
    rk = composite_risk_nd(members)
    ctrl = composite_risk(ctrl_t)
    lo = np.minimum(np.percentile(rk, 10, axis=0), ctrl)
    hi = np.maximum(np.percentile(rk, 90, axis=0), ctrl)
    conf = np.clip(1.0 - (hi - lo) / 0.5, 0.0, 1.0)
    return EnsStats(lo.astype(np.float32), hi.astype(np.float32), conf.astype(np.float32),
                    (rk >= 0.5).mean(axis=0).astype(np.float32))