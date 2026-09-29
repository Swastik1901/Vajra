"""Drop-in ONNX runtime. Export any model with input (N, 9) float32 and output (N, 4) float32."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import NowcastModel


class OnnxNowcastModel(NowcastModel):
    def __init__(self, path: str):
        import onnxruntime as ort  # optional dependency

        self.session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.name = f"onnx:{Path(path).name}"
        self.version = "user"

    def predict(self, x: np.ndarray) -> np.ndarray:
        out = self.session.run(None, {self.input_name: x.astype(np.float32)})[0]
        if out.ndim != 2 or out.shape[1] != 4:
            raise ValueError(f"ONNX model must return (N, 4); got {out.shape}")
        return out.astype(np.float32)
