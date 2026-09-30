from fastapi.testclient import TestClient

from app.core.cities import in_india, nearest_city, region_name
from app.core.config import settings
from app.services.engine import NowcastEngine
from main import app

MUMBAI = (19.08, 72.88)


def test_gazetteer():
    assert nearest_city(22.57, 88.36)["name"] == "Kolkata"
    assert region_name(22.8, 88.3) == "Kolkata region"
    assert in_india(*MUMBAI) and not in_india(51.5, -0.1)


def test_engine_switch_region_is_consistent():
    e = NowcastEngine(settings)
    e.compute_tick()
    first = e.state.region.id
    e.switch_region(*MUMBAI)
    st = e.state
    assert st.region.id != first and st.region.name == "Mumbai region"
    assert len(st.risk) == st.region.grid.n == len(st.raw)
    assert any(p["name"] == "Mumbai" for p in st.region.places)
    assert len(e.explain_cell(3)) and len(e.frame_json(60)) > 1000
    info = e.point_info(*MUMBAI)
    assert info["in_domain"] and len(info["forecast"]) == 9 and info["nearest"]["name"] == "Mumbai"


def test_point_outside_domain_and_region_api():
    with TestClient(app) as c:
        far = c.get("/api/point", params={"lat": 28.6, "lon": 77.2}).json()
        assert far["in_india"] and not far["in_domain"] and far["forecast"] == []
        assert c.post("/api/region", json={"lat": 51.5, "lon": -0.1}).status_code == 422
        cfg = c.post("/api/region", json={"lat": 28.6, "lon": 77.2}).json()
        assert cfg["region_name"] == "Delhi region"
        assert c.get("/api/grid").json()["region_id"] == cfg["region_id"]
        assert c.get("/api/point", params={"lat": 28.6, "lon": 77.2}).json()["in_domain"]
        with c.websocket_connect("/ws/stream") as ws:
            f = ws.receive_json()
            assert f["region_id"] == cfg["region_id"] and len(f["cells"]) == cfg["n_cells"]