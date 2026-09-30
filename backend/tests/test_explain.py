import numpy as np

from app.core.config import ZONES, settings
from app.services.engine import NowcastEngine
from app.services.explain import explain
from app.services.scoring import zone_index


def _s(**kw):
    base = dict(risk=0.4, dbz=45, lightning=10, cth_k=230, cooling=-2, wind=12, n_cells=10)
    base.update(kw)
    return base


def test_zone_boundaries():
    z = zone_index(np.array([0.0, 0.14, 0.15, 0.49, 0.5, 0.75, 0.95, 1.0]))
    assert z.tolist() == [0, 0, 1, 2, 3, 4, 5, 5]
    assert len(ZONES) == 6


def test_explain_up_lists_all_five_drivers():
    before = _s()
    now = _s(risk=0.7, dbz=52, lightning=18, cth_k=222, n_cells=14, wind=17)
    w = explain(now, before, 10)
    assert w["direction"] == "up"
    assert [d["key"] for d in w["drivers"]] == ["reflectivity", "lightning", "cloud_top", "area", "velocity"]


def test_explain_down_and_steady():
    before = _s(risk=0.7, dbz=55)
    assert explain(_s(risk=0.4, dbz=48), before, 10)["direction"] == "down"
    assert explain(_s(risk=0.71), before, 10)["direction"] == "steady"
    assert explain(_s(), None, 0)["drivers"] == []


def test_engine_produces_storm_why_and_cell_explain():
    e = NowcastEngine(settings)
    for _ in range(12):
        e.compute_tick()
    assert e.state.storms and all("why" in s for s in e.state.storms)
    assert '"why"' in e.frame_json(0) and '"members"' not in e.frame_json(0)
    assert set(e.explain_cell(5)) >= {"direction", "drivers", "risk_now"}