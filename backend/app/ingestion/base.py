"""Contract every raw-data source must satisfy (simulator today, DWR/INSAT/lightning tomorrow)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

import numpy as np


class RawSource(Protocol):
    sim_time: datetime

    def step(self, dt_min: float) -> None:
        """Advance / fetch the newest observation window."""

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]:
        """Return one array per name in `core.config.FEATURES`, regridded onto the given cell centres."""
