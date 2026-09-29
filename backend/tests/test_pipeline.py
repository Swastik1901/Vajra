import numpy as np
from fastapi.testclient import TestClient

from app.core.config import FEATURES, settings
from app.fusion.grid import HexGrid
from app.models.mock import MockConvectiveModel
from app.services.advection import forecast_targets
from main import app


def test_grid_and_chunks():
    g = HexGrid(settings.bbox, settings.h3_res, settings.chunk_res)
    assert g.n > 500
    assert sum(len(c) for c in g.chunks.values()) == g.n          # every cell in exactly one chunk
    assert (g.lookup(g.lat[:20], g.lon[:20]) == np.arange(20)).all()


def test_mock_model_shape_and_range():
    x = np.zeros((10, len(FEATURES)), dtype=np.float32)
    y = MockConvectiveModel().predict(x)
    assert y.shape == (10, 4) and np.isfinite(y).all()


def test_advection_moves_field_downwind():
    g = HexGrid(settings.bbox, settings.h3_res, settings.chunk_res)
    y = np.zeros((g.n, 4), dtype=np.float32)
    src = g.n // 2
    y[src] = 50
    u, v = np.full(g.n, 10.0), np.zeros(g.n)                     # eastward wind
    out = forecast_targets(g, y, u, v, 60)
    dst = int(np.argmax(out[:, 0]))
    assert g.lon[dst] > g.lon[src]


def test_api_end_to_end():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        cfg = c.get("/api/config").json()
        assert len(cfg["targets"]) == 4
        snap = c.get("/api/snapshot?horizon=60").json()
        assert len(snap["features"]) == cfg["n_cells"]
        r = c.post("/api/ingest", json={"observations": [{"lat": 22.57, "lon": 88.36, "values": {"dbz": 60}}]})
        assert r.json()["applied"] == 1
        with c.websocket_connect("/ws/stream") as ws:
            ws.send_json({"horizon": 30})
            frames = [ws.receive_json() for _ in range(2)]
            assert frames[-1]["type"] == "frame" and len(frames[-1]["cells"]) == cfg["n_cells"]
