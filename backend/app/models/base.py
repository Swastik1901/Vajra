"""Model contract. Anything with `predict((N, len(FEATURES))) -> (N, 4)` can be dropped in."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class NowcastModel(ABC):
    name: str = "unnamed"
    version: str = "0"

    @abstractmethod
    def predict(self, x: np.ndarray) -> np.ndarray:
        """x: float32 (N, F) in `core.config.FEATURES` order.
        returns float32 (N, 4) in `core.config.TARGETS` order:
        [lightning strikes/km2/hr, hail prob %, downburst gust km/h, cloudburst prob %]."""
