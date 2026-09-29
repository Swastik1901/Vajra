"""Semi-Lagrangian nowcast: where will today's hazard field be in `minutes`?

value_forecast(x, t+T) = value_now(x - wind * T)   -> then diffuse (growing uncertainty) and decay.
"""
from __future__ import annotations

import numpy as np

from ..fusion.grid import HexGrid

M_PER_DEG = 111_320.0
# e-folding lifetime (minutes) per target: lightning, hail, downburst, cloudburst
TAU_MIN = np.array([400.0, 500.0, 350.0, 450.0])


def forecast_targets(grid: HexGrid, y: np.ndarray, u: np.ndarray, v: np.ndarray, minutes: float) -> np.ndarray:
    if minutes <= 0:
        return y
    dt = minutes * 60.0
    lat_up = grid.lat - v * dt / M_PER_DEG
    lon_up = grid.lon - u * dt / (M_PER_DEG * np.cos(np.radians(grid.lat)))
    idx = grid.lookup(lat_up, lon_up)
    adv = np.where((idx >= 0)[:, None], y[np.maximum(idx, 0)], 0.0)
    a = min(0.6, minutes / 360.0 * 0.8)           # diffusion grows with lead time
    out = (1 - a) * adv + a * grid.neighbor_mean(adv)
    out = out * np.exp(-minutes / TAU_MIN)
    return out.astype(np.float32)
