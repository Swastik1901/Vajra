"""Example: export a tiny (untrained) MLP as ONNX to prove the drop-in path works.
Needs `pip install torch onnx onnxruntime`. Output values are NOT meaningful; replace with your trained net.

    python scripts/make_dummy_onnx.py && MODEL_PATH=models_weights/dummy.onnx uvicorn main:app --port 8000
"""
import os

import torch
import torch.nn as nn

os.makedirs("models_weights", exist_ok=True)
net = nn.Sequential(nn.Linear(9, 32), nn.ReLU(), nn.Linear(32, 4), nn.Softplus()).eval()
torch.onnx.export(
    net, torch.zeros(1, 9), "models_weights/dummy.onnx",
    input_names=["features"], output_names=["targets"],
    dynamic_axes={"features": {0: "n"}, "targets": {0: "n"}}, opset_version=17,
)
print("wrote models_weights/dummy.onnx")
