# Convective storm nowcasting: 0–6 h hyper-local GIS dashboard

End-to-end system: streaming environmental data → H3 spatial tiling → modular ML inference → WebSocket/REST → interactive deck.gl map with risk zones and wind-driven drift.

See **INSTALLATION.md** for setup. Short version: `uvicorn main:app --port 8000` in `backend/`, `npm install && npm run dev` in `frontend/`.

## Data Flow

```
 RawSource (simulator | DWR + INSAT + lightning via Kafka)
      │  per-cell raw features (dbz, vil, cloud-top temp/cooling, CAPE, wind u/v, lightning, humidity)
      ▼
 HexGrid (H3 res 6-8)  ── parent hexes (res 4) = independent chunks
      │  X: (N cells × 9 features)
      ▼
 Chunked inference (thread pool, one task per chunk)   NowcastModel.predict → Y: (N × 4)
      │  [lightning, hail %, downburst km/h, cloudburst %]     mock | ONNX | TorchScript
      ▼
 Scoring + tracking: composite risk 0..1, storm detection, stable IDs, ETA to places
      ▼
 Advection (semi-Lagrangian): Y at t+15…360 min = Y(x − wind·T), with diffusion + decay
      ▼
 FastAPI ── GET /api/grid (static geometry, once)
         ── WS  /ws/stream (frame per tick, client picks horizon)
         ── GET /api/snapshot (GeoJSON polling), POST /api/ingest (real observations)
      ▼
 Next.js + deck.gl + MapLibre: hex fill · heat glow · wind particles · drift arrows · storm cells · ETA clocks · cell inspector
```

Why FastAPI: the workload is NumPy/ONNX/PyTorch-bound, so Python keeps the ML and geo stack (H3, Py-ART, Xarray) in one process. Async I/O handles many WebSocket clients, and heavy work runs in threads.

Why the geometry is sent once: hex polygons never change, so each frame carries only values (about 330 KB per frame at 1,500 cells).

## Directory structure

```
convective-nowcasting/
├── README.md · INSTALLATION.md
├── backend/
│   ├── main.py                     FastAPI app, lifespan starts the engine loop
│   ├── requirements.txt
│   ├── app/
│   │   ├── core/config.py          FEATURES, TARGETS, ZONES, env settings · cities.py (gazetteer)
│   │   ├── ingestion/              simulator.py (mock stream) · sensors.py (sources, faults) · base.py · real_feed_stub.py
│   │   ├── fusion/                 grid.py (H3 lattice, chunks, lookup) · reliability.py (fusion)
│   │   ├── models/                 base.py · mock.py · onnx_runner.py · torch_runner.py · registry.py
│   │   ├── services/               engine.py (pipeline) · advection.py · tracking.py · scoring.py · explain.py · twin.py · lead_time.py · ensemble.py
│   │   └── api/                    routes.py (REST) · ws.py (WebSocket)
│   ├── scripts/make_dummy_onnx.py
│   └── tests/test_pipeline.py
└── frontend/
    ├── package.json · tsconfig.json · tailwind.config.js · next.config.mjs
    └── src/
        ├── app/                    layout.tsx · page.tsx · globals.css
        ├── components/             MapViewer · ControlPanel · HazardLegend · CellTelemetry · ETACountdown · RiskDrivers · WhyList · RegionSummary · StormTwinCard · SensorHealth
        ├── hooks/                  useNowcastStream (WS) · useWindParticles · useCellExplain
        └── lib/                    types · api · colors · metrics · viewport
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/config` | Domain, feature and target schema, places, horizons, model info |
| `GET /api/grid` | Static GeoJSON hex polygons (`i`, `id`, `chunk`, `lat`, `lon`) |
| `GET /api/snapshot?horizon=0..360` | GeoJSON with `risk`, 4 targets, `wind_u`, `wind_v`, `wind_speed_ms`, `wind_dir_deg` |
| `POST /api/ingest` | `{"observations":[{"lat":22.57,"lon":88.36,"values":{"dbz":60}}],"ttl_ticks":5}` overrides simulated values |
| `GET /api/point?lat=&lon=` | Click-a-spot summary: nearest city, risk now, 6 h outlook, storm arrival at that spot |
| `POST /api/region` | `{"lat":13.08,"lon":80.27}` re-centres the monitored box (India only, shared by all viewers) |
| `GET /api/sensors` | Health of each source and how the fused inputs were obtained |
| `POST /api/faults` / `DELETE /api/faults` | `{"source":"radar","mode":"outage|partial|noisy","duration_ticks":30}` breaks a sensor on purpose / clears all |
| `GET /api/explain/cell/{i}` | Drivers of the recent risk change for one cell |
| `WS /ws/stream` | Server pushes a frame per tick. Client sends `{"horizon": 60}` to change lead time. |

Frame cell format (index-aligned with `/api/grid`): `r` risk, `t` `[lightning, hail, downburst, cloudburst]`, `w` `[u, v]` m/s, `x` fused inputs in `config.features` order, `lo`/`hi` risk range, `c` confidence, `p` chance of Warning or worse, `q` data quality.

## The five differentiators, and what each one really is

| # | Feature | Where | What it does | Honest limit |
| --- | --- | --- | --- | --- |
| 1 | **Storm digital twin** | `services/twin.py`, `StormTwinCard.tsx`, map tracks | One living record per storm: past track, risk history, lifecycle stage (initiating / intensifying / mature / weakening), speed and heading, peak intensity, estimated end of life, projected path with a widening uncertainty cone, list of recently ended storms | Stage and end of life come from simple trend rules on risk. "Tracked for" counts from first detection, not true birth. |
| 2 | **Lead-time adaptive forecasting** | `services/lead_time.py` | Three methods blended by lead time: extrapolation (mostly 0-1 h), storm-lifecycle object model (1-3 h), environment potential from CAPE and humidity (3-6 h). The ControlPanel shows the current mix. | Blend weights are hand-designed smooth functions, not learned. With verification data, fit them per lead time. |
| 3 | **Reliability-aware fusion** | `ingestion/sensors.py`, `fusion/reliability.py`, `SensorHealth.tsx` | Four simulated sources (radar, satellite, lightning, NWP) with their own cadence, outages, blind spots and noise episodes. Every input gets a value, a reliability and a provenance (measured / proxy / last value / neighbour fill / default). Noisy data is down-weighted, gaps are filled from other sensors, neighbours or the last good value. | Faults are simulated. Proxy formulas (for example cloud-top temperature to reflectivity) encode the simulator's physics and must be re-fitted on real data. |
| 4 | **Explainable forecasting** | `services/explain.py`, `WhyList.tsx` | "Risk increase caused by: reflectivity, lightning, cloud-top cooling, area, velocity", for storms and single cells | Rule-based on observed change over about 10 min, not model attribution. Velocity is a peak-wind proxy. |
| 5 | **Confidence-aware predictions** | `services/ensemble.py` | Every cell has risk, a 10th-90th percentile range, a confidence level and the chance of a Warning zone or worse. Unreliable inputs and longer lead times widen the range. Map can be coloured by **Uncertainty** or **Data quality**. | A 12-member perturbation ensemble with engineered spreads. It is not calibrated against observed outcomes. |

Try it: open **Sensor reliability** (bottom right), press *Radar outage*, and watch data quality drop, the input mix switch to proxy or last-value fills, and the confidence ranges widen. *Clear faults* restores it. Random faults also start by themselves at `FAULT_RATE` per source per tick (default 0.006; set 0 to disable).

## Demo controls: calm mode and pause

* `CALM=1` slows and steadies the simulation for presentations: 6 s frames, 1 simulated minute per frame, about 12 % of the per-frame noise, one fixed ensemble seed, no random sensor faults. Storms still move.
* **Pause / Resume** (left panel, `POST /api/pause` and `/api/resume`) freezes the state. The lead-time slider keeps working on the frozen state, and ETA clocks stop.
* The panel shows a **Simulated data** chip at all times so nobody mistakes the demo for a live weather feed.
* Storm arrows: one arrow per storm (direction of travel), plus a line to the storm's projected position when the slider is past "Now".

## Any region: click the map, or use your location

There is no region dropdown. Interaction is on the map itself:

* **Click a spot inside the current area**: a panel shows the nearest city ("14 km NE of Barasat"), the warning zone, model outputs, a 6-hour risk outlook (bars coloured by zone), and any storm heading for that exact spot.
* **Click outside the current area (anywhere in India)**: the backend rebuilds the H3 grid as a 2.6° × 2.0° box centred there, restarts the simulator, and the map flies to it. Cities inside the new box get storm-arrival clocks.
* **Use my location** (left panel): browser geolocation, then the same flow. It needs `localhost` or HTTPS, and the user must allow the permission.
* The zoom is chosen automatically so the whole box fits the screen.

Notes and limits:

* The monitored region is **shared by everyone connected to the same backend**. If one viewer switches region, others follow. Per-user regions would need one engine per region or a cache of engines.
* Coverage is limited to a rough bounding box of India (`INDIA` in `core/cities.py`). Outside it, `POST /api/region` returns 422.
* City names come from a small built-in list of about 110 Indian cities with approximate coordinates (`core/cities.py`). It is not a full gazetteer, so a click far from any listed city is labelled relative to the nearest one. Add rows to `CITIES` for finer labels.
* Storms are still simulated in every region. Real data needs a feed that covers that region.
* The startup region is set by `BBOX`; the size of a clicked region is `REGION_SPAN` in `core/config.py`.

## Warning zones (colour coding)

Combined risk (0..1) maps to six categorical zones, defined once in `backend/app/core/config.py` (`ZONES`) and served in `/api/config`, so the map, legend, ETA dots and REST snapshot always agree.

| Zone | Risk from | Meaning |
| --- | --- | --- |
| Blue · Low | 0.00 | No significant convection |
| Green · Developing | 0.15 | Isolated cells forming |
| Yellow · Watch | 0.30 | Thunderstorms possible |
| Orange · Warning | 0.50 | Intense cell, lightning, heavy rain |
| Red · Severe | 0.70 | Hail, damaging gusts, flash-flood risk |
| Purple · Extreme | 0.88 | Life-threatening |

Change thresholds or colours in `ZONES` only. The dashboard has a **Warning zones / Smooth gradient** switch, and the legend shows the area (km²) in each zone for the selected metric. `/api/snapshot` adds a `zone` key per cell.

## Explaining the change in the forecast

For every tracked storm the engine compares its footprint now with about 10 simulated minutes ago (`EXPLAIN_LAG_TICKS`, default 5 ticks) and lists the drivers that crossed a threshold:

* Reflectivity increased (≥ 3 dBZ)
* Lightning density increased (≥ 15 % and ≥ 1.5 strikes/km²/hr)
* Cloud-top cooled rapidly (≥ 3 K colder, or cooling faster than 8 K/15 min)
* Storm area expanded (≥ 10 %)
* Velocity pattern intensified (peak wind up ≥ 2 m/s)

If risk falls, the same checks run in reverse ("Risk decrease caused by"). Thresholds live in `backend/app/services/explain.py`. Storm explanations arrive inside every WebSocket frame (`storms[].why`); a single cell's explanation is `GET /api/explain/cell/{i}`. The "velocity" driver uses peak wind speed in the footprint, the closest proxy to radar velocity in the simulated data.

## Plug in a real model

1. Train on the 9-feature input, 4-target output defined in `core/config.py` (`FEATURES`, `TARGETS`). A per-cell MLP works directly. For ConvLSTM, UNet or TrajGRU, wrap the spatial context inside your exported graph.
2. Export input `(N, 9)` float32 to output `(N, 4)` float32 as ONNX or TorchScript.
3. `pip install onnxruntime` (or `torch`), then `MODEL_PATH=/path/model.onnx uvicorn main:app --port 8000`.

The registry falls back to the mock model with a log warning if loading fails. To rename or replace targets, edit `TARGETS` and `models/mock.py`. The frontend reads labels, units and ranges from `/api/config`.

`scripts/make_dummy_onnx.py` shows the export shape. I did not run it in my sandbox because it needs torch.

## Honest limits of this build

* The data is **simulated**. `real_feed_stub.py` marks where DWR, INSAT and lightning consumers go. Nothing here reads real IMD feeds yet.
* The mock model is a heuristic, not a trained network. The 0–6 h forecast is advection plus diffusion of the current hazard field, not a learned spatiotemporal prediction. It shows the plumbing and UI, not forecast skill.
* Not yet production-hardened. Before deploying, add: auth and rate limits, Kafka (or similar) ingest, Redis pub/sub so multiple API workers share frames, binary or vector-tile frames for res 7–8 domains, monitoring, and validation against radar and lightning ground truth.
