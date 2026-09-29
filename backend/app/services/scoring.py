from __future__ import annotations

import numpy as np

from ..core.config import TARGETS

_LO = np.array([t["lo"] for t in TARGETS])
_HI = np.array([t["hi"] for t in TARGETS])


def normalize_targets(y: np.ndarray) -> np.ndarray:
    return np.clip((y - _LO) / (_HI - _LO), 0.0, 1.0)


def composite_risk(y: np.ndarray) -> np.ndarray:
    """0..1 risk = worst normalised hazard in the cell."""
    return normalize_targets(y).max(axis=1)


def dominant_hazard(y_row: np.ndarray) -> str:
    return TARGETS[int(np.argmax(normalize_targets(y_row[None, :])[0]))]["key"]
