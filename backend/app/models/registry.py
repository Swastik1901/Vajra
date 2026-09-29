from __future__ import annotations

import logging
from pathlib import Path

from .base import NowcastModel
from .mock import MockConvectiveModel

log = logging.getLogger("nowcast.models")


def load_model(path: str | None) -> NowcastModel:
    """`.onnx` -> ONNX Runtime, `.pt/.ts` -> TorchScript, otherwise (or on any failure) -> mock."""
    if path and Path(path).exists():
        try:
            if path.endswith(".onnx"):
                from .onnx_runner import OnnxNowcastModel
                return OnnxNowcastModel(path)
            if path.endswith((".pt", ".ts")):
                from .torch_runner import TorchNowcastModel
                return TorchNowcastModel(path)
        except Exception as exc:  # missing runtime, bad graph, ...
            log.warning("Could not load model %s (%s); falling back to mock.", path, exc)
    elif path:
        log.warning("MODEL_PATH %s not found; using mock model.", path)
    return MockConvectiveModel()
