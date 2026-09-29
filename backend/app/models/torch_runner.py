"""Drop-in TorchScript runtime (torch.jit.trace / script output)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import NowcastModel


class TorchNowcastModel(NowcastModel):
    def __init__(self, path: str):
        import torch  # optional dependency

        self.torch = torch
        self.module = torch.jit.load(path, map_location="cpu").eval()
        self.name = f"torchscript:{Path(path).name}"
        self.version = "user"

    def predict(self, x: np.ndarray) -> np.ndarray:
        with self.torch.no_grad():
            y = self.module(self.torch.from_numpy(x.astype(np.float32))).numpy()
        if y.ndim != 2 or y.shape[1] != 4:
            raise ValueError(f"TorchScript model must return (N, 4); got {y.shape}")
        return y.astype(np.float32)
