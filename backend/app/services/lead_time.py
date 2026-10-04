"""Lead-time adaptive forecasting: three experts, blended with weights that depend on how far ahead we look.

  0-1 h   extrapolation : advect the observed hazard field, scaled by each storm's intensity trend
  1-3 h   storm lifecycle: object-based. Each storm's digital twin is moved along its projected track
                           and faded according to its lifecycle stage / estimated end of life
  3-6 h   environment   : convective potential from CAPE and humidity, moved with the flow and widened

The weights are hand-designed smooth functions of lead time (documented here), not learned. With
verification data they would be fitted per lead time.
"""
from __future__ import annotations

import math

import numpy as np

from ..core.config import FEATURES
from ..fusion.grid import HexGrid
from .advection import M_PER_DEG, forecast_targets
from .twin import EOL_DEFAULT, interp_track

KEYS = ("extrapolation", "lifecycle", "environment")
_I = {f: i for i, f in enumerate(FEATURES)}


def _sig(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def strategy_weights(minutes: float) -> dict[str, float]:
    t = float(minutes)
    a = 1.0 / (1.0 + (t / 80.0) ** 3)
    b = 0.9 * math.exp(-(((t - 150.0) / 70.0) ** 2))
    c = min(1.0, (t / 300.0) ** 2)
    s = a + b + c
    return {"extrapolation": a / s, "lifecycle": b / s, "environment": c / s}


def expert_extrapolation(grid: HexGrid, st, minutes: float) -> np.ndarray:
    y = st.targets.copy()
    for s in st.storms:
        tw = s.get("twin")
        if not tw:
            continue
        rel = tw["trend_per_10min"] / max(s["risk"], 0.3)
        f = float(np.clip(1.0 + 0.5 * rel * min(minutes, 60.0) / 10.0, 0.5, 1.4))
        y[s["members"]] *= f
    return forecast_targets(grid, y, st.u, st.v, minutes)


def expert_lifecycle(grid: HexGrid, st, minutes: float) -> np.ndarray:
    out = np.zeros_like(st.targets)
    coslat = np.cos(np.radians(grid.lat))
    for s in st.storms:
        tw = s["twin"]
        lat, lon = interp_track(tw["track_future"], minutes)
        eol = tw["eol_min"] if tw["eol_min"] is not None else EOL_DEFAULT[tw["stage"]]
        amp = 1.0 if minutes <= eol else math.exp(-(minutes - eol) / 40.0)
        grow = 1.0 + (0.15 if tw["stage"] in ("initiating", "intensifying") else -0.10 if tw["stage"] == "weakening" else 0.05) * minutes / 60.0
        r = max(s["radius_km"] * max(grow, 0.6), 4.0)
        dy = (grid.lat - lat) * 111.32
        dx = (grid.lon - lon) * 111.32 * coslat
        g = np.exp(-(dx * dx + dy * dy) / (2 * r * r))
        out = np.maximum(out, np.asarray(s["peak_targets"])[None, :] * g[:, None] * amp)
    return out


def expert_environment(grid: HexGrid, st, minutes: float) -> np.ndarray:
    cape, hum = st.raw[:, _I["cape"]], st.raw[:, _I["humidity"]]
    p = _sig((cape - 1800.0) / 500.0) * _sig((hum - 62.0) / 8.0)
    dt = minutes * 60.0
    idx = grid.lookup(grid.lat - st.v * dt / M_PER_DEG, grid.lon - st.u * dt / (M_PER_DEG * np.cos(np.radians(grid.lat))))
    p = np.where(idx >= 0, p[np.maximum(idx, 0)], 0.0)
    for _ in range(3):
        p = 0.5 * p + 0.5 * grid.neighbor_mean(p)
    speed = float(np.median(np.hypot(st.u, st.v)))   # background flow only: today's outflow rings do not persist for hours
    return np.stack([14.0 * p, 30.0 * p, 1.2 * 3.6 * speed + 25.0 * p, 28.0 * p], axis=1)


def blend_forecast(grid: HexGrid, st, minutes: float) -> np.ndarray:
    if minutes <= 0:
        return st.targets
    w = strategy_weights(minutes)
    y = w["extrapolation"] * expert_extrapolation(grid, st, minutes)
    y = y + w["lifecycle"] * expert_lifecycle(grid, st, minutes)
    y = y + w["environment"] * expert_environment(grid, st, minutes)
    return y.astype(np.float32)