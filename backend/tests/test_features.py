"""Digital twin, lead-time adaptation, reliability-aware fusion, confidence-aware predictions."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi.testclient import TestClient

from app.core.config import FEATURES, settings
from app.models.mock import MockConvectiveModel
from app.services.engine import NowcastEngine
from app.services.ensemble import ensemble_stats, input_ensemble
from app.services.lead_time import strategy_weights
from app.services.scoring import composite_risk
from main import app

I = {f: i for i, f in enumerate(FEATURES)}


def warm(n=20) -> NowcastEngine:
    e = NowcastEngine(settings)
    for _ in range(n):
        e.compute_tick()
    return e


# ---------------------------------------------------------------- reliability-aware fusion
def test_healthy_inputs_are_fully_observed_and_high_quality():
    e = warm()
    assert e.state.fusion["mean_quality"] > 0.95 and e.state.fusion["mix"]["observed"] == 100.0


def test_lightning_outage_is_filled_and_lowers_quality():
    e = warm()
    base = e.state.fusion["mean_quality"]
    e.inject_fault("lightning", "outage", 30)
    for _ in range(8):
        e.compute_tick()
    st = e.state
    assert np.isfinite(st.raw).all()                         # no gaps reach the model
    assert st.fusion["mean_quality"] < base
    assert (st.prov[:, I["lightning"]] != 0).all()           # none of it is a direct observation
    assert st.sensors[2]["status"] == "outage"


def test_radar_outage_uses_satellite_proxy_with_small_error():
    e = warm()
    e.inject_fault("radar", "outage", 30)
    for _ in range(10):
        e.compute_tick()
    st = e.state
    assert (st.prov[:, I["dbz"]] == 1).mean() > 0.9          # proxy from cloud-top temperature
    truth = e.source.sample(st.region.grid.lat, st.region.grid.lon)["dbz"]
    assert np.abs(st.raw[:, I["dbz"]] - truth).mean() < 3.0


def test_noisy_source_gets_lower_reliability():
    e = warm()
    e.inject_fault("satellite", "noisy", 30)
    for _ in range(6):
        e.compute_tick()
    assert e.state.rel[:, I["cth_k"]].mean() < 0.6
    assert e.state.rel[:, I["dbz"]].mean() > 0.9


def test_partial_outage_reduces_availability_and_is_inpainted():
    e = warm()
    e.inject_fault("radar", "partial", 30)
    for _ in range(6):
        e.compute_tick()
    radar = e.state.sensors[0]
    assert radar["status"] == "partial outage" and radar["availability_pct"] < 100
    assert np.isfinite(e.state.raw).all()


# ---------------------------------------------------------------- confidence-aware predictions
def test_unreliable_inputs_widen_the_ensemble():
    m = MockConvectiveModel()
    x = np.zeros((200, len(FEATURES)), dtype=np.float32)
    x[:, I["dbz"]], x[:, I["vil"]], x[:, I["cth_k"]] = 50, 35, 225
    x[:, I["cape"]], x[:, I["humidity"]], x[:, I["wind_u"]] = 2500, 85, 10
    with ThreadPoolExecutor(2) as pool:
        good = input_ensemble(m, x, np.ones_like(x), pool, 12, np.random.default_rng(1))
        bad = input_ensemble(m, x, np.full_like(x, 0.1), pool, 12, np.random.default_rng(1))
    spread = lambda y: composite_risk(y.reshape(-1, 4)).reshape(y.shape[:2]).std(axis=0).mean()
    assert spread(bad) > 1.5 * spread(good)


def test_ensemble_bounds_and_spread_grows_with_lead_time():
    e = warm()
    st = e.state
    for t in (0, 60, 240):
        y, risk = e._forecast(st, t)
        s = e._ens(st, t)
        assert (s.lo <= risk + 1e-6).all() and (s.hi >= risk - 1e-6).all()
        assert (s.conf >= 0).all() and (s.conf <= 1).all() and (s.p >= 0).all() and (s.p <= 1).all()
    # same hazard field, only the lead time changes: position/amplitude error must widen the range
    g, hot = st.region.grid, st.risk >= 0.15
    spread = lambda t: float((lambda s: (s.hi - s.lo)[hot].mean())(
        ensemble_stats(g, st.targets, st.targets, st.ens0, st.u, st.v, t, 7)))
    assert spread(0) < spread(120) and spread(0) < spread(360)      # grows, then may saturate


# ---------------------------------------------------------------- lead-time adaptive AI
def test_strategy_weights_shift_with_lead_time():
    for t in (0, 30, 90, 180, 360):
        assert abs(sum(strategy_weights(t).values()) - 1) < 1e-9
    assert strategy_weights(15)["extrapolation"] > 0.9
    assert strategy_weights(150)["lifecycle"] > 0.5
    assert strategy_weights(360)["environment"] > 0.9


def test_forecast_at_zero_is_the_analysis_and_changes_with_lead():
    e = warm(30)
    st = e.state
    assert np.array_equal(e._forecast(st, 0)[0], st.targets)
    assert not np.allclose(e._forecast(st, 120)[0], st.targets)


# ---------------------------------------------------------------- storm digital twin
def test_storm_twins_have_lifecycle_track_and_projection():
    e = warm(30)
    storms = e.state.storms
    assert storms
    for s in storms:
        tw = s["twin"]
        assert tw["stage"] in ("initiating", "intensifying", "mature", "weakening")
        assert len(tw["track_future"]) == 13 and tw["track_future"][0]["m"] == 0
        radii = [p["radius_km"] for p in tw["track_future"]]
        assert radii == sorted(radii)                        # uncertainty cone only widens
        assert len(tw["track_past"]) >= 1 and len(tw["risk_hist"]) >= 1


# ---------------------------------------------------------------- API
def test_api_faults_sensors_and_frame_fields():
    with TestClient(app) as c:
        eng = app.state.engine
        assert c.post("/api/faults", json={"source": "nope", "mode": "outage"}).status_code == 422
        assert c.post("/api/faults", json={"source": "radar", "mode": "bad"}).status_code == 422
        assert c.post("/api/faults", json={"source": "radar", "mode": "outage", "duration_ticks": 20}).json()["ok"]
        eng.compute_tick()
        sens = c.get("/api/sensors").json()
        assert sens["sources"][0]["status"] == "outage" and "mix" in sens["fusion"]
        with c.websocket_connect("/ws/stream") as ws:
            f = ws.receive_json()
        assert set(f["cells"][0]) >= {"r", "t", "w", "x", "lo", "hi", "c", "p", "q"}
        assert set(f["strategy"]["weights"]) == {"extrapolation", "lifecycle", "environment"}
        if f["storms"]:
            assert "twin" in f["storms"][0] and "conf" in f["storms"][0]
        pt = c.get("/api/point", params={"lat": 22.57, "lon": 88.36}).json()
        assert "conf" in pt["forecast"][0] and len(pt["quality"]["features"]) == len(FEATURES)
        assert c.delete("/api/faults").json()["ok"]