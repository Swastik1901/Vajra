import dataclasses

import numpy as np
from fastapi.testclient import TestClient

from app.core.config import FEATURES, settings
from app.services.engine import NowcastEngine
from main import app


def engine(calm: bool) -> NowcastEngine:
    s = dataclasses.replace(settings, calm=calm, fault_rate=0.0)
    e = NowcastEngine(s)
    for _ in range(6):
        e.compute_tick()
    return e


def test_calm_mode_removes_frame_to_frame_jitter_but_storms_still_move():
    normal, calm = engine(False), engine(True)
    d = FEATURES.index("dbz")

    def jitter(e):
        a = e.state.raw[:, d].copy()
        e.compute_tick()
        b = e.state.raw[:, d]
        quiet = (a < 12) & (b < 12)                       # background cells: only noise changes there
        return float(np.abs(a - b)[quiet].mean())

    assert jitter(calm) < 0.3 * jitter(normal)
    before = [(s["lat"], s["lon"]) for s in calm.state.storms]
    for _ in range(5):
        calm.compute_tick()
    assert before != [(s["lat"], s["lon"]) for s in calm.state.storms]      # still a moving simulation


def test_calm_uses_fixed_ensemble_seed_and_slower_ticks():
    c = dataclasses.replace(settings, calm=True)
    e = NowcastEngine(c)
    assert e._ens_seed(3, 60) == e._ens_seed(900, 60)
    normal = NowcastEngine(dataclasses.replace(settings, calm=False))
    assert normal._ens_seed(3, 60) != normal._ens_seed(900, 60)          # normal mode reseeds every tick


def test_pause_freezes_ticks_and_flags_frames():
    e = engine(False)
    tick = e.state.tick
    e.set_paused(True)
    assert e.step_if_running() is False and e.state.tick == tick
    assert '"paused":true' in e.frame_json(0)
    assert e.frame_json(120) and e.state.tick == tick                      # slider still works while frozen
    e.set_paused(False)
    assert e.step_if_running() is True and e.state.tick == tick + 1


def test_pause_resume_api():
    with TestClient(app) as c:
        assert c.post("/api/pause").json() == {"paused": True}
        with c.websocket_connect("/ws/stream") as ws:
            assert ws.receive_json()["paused"] is True
        assert c.post("/api/resume").json() == {"paused": False}
        assert "calm" in c.get("/api/config").json()


def test_values_held_between_satellite_frames_do_not_decay():
    """Regression: held cloud-top temperature used to drift toward climatology between 3-tick satellite frames."""
    e = engine(True)
    c = FEATURES.index("cth_k")
    series = []
    for _ in range(9):
        e.compute_tick()
        series.append(float(e.state.raw[:, c].min()))
    assert max(series) - min(series) < 6.0           # was a 20+ K sawtooth