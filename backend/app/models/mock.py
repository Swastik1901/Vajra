"""Heuristic stand-in for the trained network. Same I/O contract as a real model."""
from __future__ import annotations

import numpy as np

from ..core.config import FEATURES
from .base import NowcastModel


def _sig(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class MockConvectiveModel(NowcastModel):
    name = "mock-convective-heuristic"
    version = "0.1"

    def predict(self, x: np.ndarray) -> np.ndarray:
        f = {k: x[:, i].astype(np.float64) for i, k in enumerate(FEATURES)}
        dbz, vil, cth, cool = f["dbz"], f["vil"], f["cth_k"], f["cooling_k15"]
        cape, u, v, ltg, hum = f["cape"], f["wind_u"], f["wind_v"], f["lightning"], f["humidity"]
        speed = np.hypot(u, v)

        lightning = 32 * _sig((dbz - 38) / 4) * np.clip(cape / 2500, 0.2, 1.3) + 0.5 * ltg
        hail = 100 * _sig((dbz - 48) / 2.5) * _sig((vil - 38) / 6) * _sig((235 - cth) / 8)
        downburst = 1.2 * 3.6 * speed + 30 * _sig((dbz - 45) / 4) * np.clip(cape / 3000, 0.2, 1.2) \
            + 0.8 * np.clip(-cool, 0, None)
        rain = (np.power(10.0, dbz / 10.0) / 200.0) ** (1 / 1.6)  # Marshall-Palmer Z=200 R^1.6 (mm/h)
        cloudburst = 100 * _sig((rain - 70) / 18) * _sig((hum - 70) / 8)

        y = np.stack([np.clip(lightning, 0, 60), np.clip(hail, 0, 100),
                      np.clip(downburst, 0, 200), np.clip(cloudburst, 0, 100)], axis=1)
        return y.astype(np.float32)
