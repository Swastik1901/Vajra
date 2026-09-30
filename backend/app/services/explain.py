"""Explainability: WHY did the risk change? Compares a region now vs `lag` ticks ago.

A "region" is either a tracked storm footprint or a single cell. Every driver has a threshold so
only meaningful changes are reported, in the same wording an operator would use on a bulletin.
"""
from __future__ import annotations

import numpy as np

from ..core.config import FEATURES

_I = {k: FEATURES.index(k) for k in FEATURES}
RISK_EPS = 0.03  # minimum |risk change| (0..1) to call a trend


def region_stats(idx: np.ndarray, raw: np.ndarray, y: np.ndarray, risk: np.ndarray, single: bool = False) -> dict:
    r = raw[idx]
    return {
        "risk": float(risk[idx].max()),
        "dbz": float(r[:, _I["dbz"]].max()),
        "lightning": float(y[idx, 0].max()),                       # strikes/km2/hr
        "cth_k": float(r[:, _I["cth_k"]].min()),                   # coldest cloud top
        "cooling": float(r[:, _I["cooling_k15"]].min()),           # fastest cooling K/15min
        "wind": float(np.hypot(r[:, _I["wind_u"]], r[:, _I["wind_v"]]).max()),  # m/s
        "n_cells": None if single else int(len(idx)),
    }


def _checks(now: dict, b: dict):
    """(key, text if intensifying, text if weakening, intensify_delta, threshold, detail)"""
    out = [
        ("reflectivity", "Reflectivity increased", "Reflectivity decreased",
         now["dbz"] - b["dbz"], 3.0, f"{b['dbz']:.0f} → {now['dbz']:.0f} dBZ"),
    ]
    dl = now["lightning"] - b["lightning"]
    out.append(("lightning", "Lightning density increased", "Lightning density decreased",
                dl / max(b["lightning"], 2.0) if abs(dl) >= 1.5 else 0.0, 0.15,
                f"{b['lightning']:.0f} → {now['lightning']:.0f} strikes/km²/hr"))
    cooled = b["cth_k"] - now["cth_k"]
    if now["cooling"] <= -8.0:            # already cooling very fast right now
        cooled = max(cooled, 3.0)
    out.append(("cloud_top", "Cloud-top cooled rapidly", "Cloud-top warmed",
                cooled, 3.0, f"{b['cth_k'] - 273.15:.0f} → {now['cth_k'] - 273.15:.0f} °C"))
    if now["n_cells"] is not None and b["n_cells"] is not None:
        dn = now["n_cells"] - b["n_cells"]
        out.append(("area", "Storm area expanded", "Storm area shrank",
                    dn / max(b["n_cells"], 1) if abs(dn) >= 1 else 0.0, 0.10,
                    f"{b['n_cells']} → {now['n_cells']} cells"))
    out.append(("velocity", "Velocity pattern intensified", "Velocity pattern weakened",
                now["wind"] - b["wind"], 2.0, f"peak wind {b['wind'] * 3.6:.0f} → {now['wind'] * 3.6:.0f} km/h"))
    return out


def explain(now: dict, before: dict | None, lag_min: float) -> dict:
    if before is None:
        return {"direction": "steady", "risk_before": None, "risk_now": round(now["risk"], 3),
                "risk_delta": 0.0, "lag_min": 0.0, "drivers": []}
    d = now["risk"] - before["risk"]
    direction = "up" if d >= RISK_EPS else "down" if d <= -RISK_EPS else "steady"
    drivers = []
    if direction != "steady":
        sign = 1 if direction == "up" else -1
        for key, up_t, down_t, delta, thr, detail in _checks(now, before):
            if sign * delta >= thr:
                drivers.append({"key": key, "text": up_t if sign > 0 else down_t, "detail": detail})
    return {"direction": direction, "risk_before": round(before["risk"], 3), "risk_now": round(now["risk"], 3),
            "risk_delta": round(d, 3), "lag_min": round(lag_min, 1), "drivers": drivers}