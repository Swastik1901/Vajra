from __future__ import annotations

import numpy as np

from ..core.config import TARGETS, ZONES

_LO = np.array([t["lo"] for t in TARGETS])
_HI = np.array([t["hi"] for t in TARGETS])
_ZONE_MIN = np.array([z["min"] for z in ZONES])


def normalize_targets(y: np.ndarray) -> np.ndarray:
    return np.clip((y - _LO) / (_HI - _LO), 0.0, 1.0)


def composite_risk(y: np.ndarray) -> np.ndarray:
    """0..1 risk = worst normalised hazard in the cell."""
    return normalize_targets(y).max(axis=1)


def dominant_hazard(y_row: np.ndarray) -> str:
    return TARGETS[int(np.argmax(normalize_targets(y_row[None, :])[0]))]["key"]


def zone_index(risk: np.ndarray) -> np.ndarray:
    """0..len(ZONES)-1 warning-zone index for each risk value."""
    return np.clip(np.searchsorted(_ZONE_MIN, risk, side="right") - 1, 0, len(ZONES) - 1)


def composite_risk_nd(y: np.ndarray) -> np.ndarray:
    """Composite risk for any leading shape, e.g. ensemble members (K, N, 4) -> (K, N)."""
    return normalize_targets(y).max(axis=-1)