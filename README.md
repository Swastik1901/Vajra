# Convective storm nowcasting: 0–6 h hyper-local GIS dashboard

End-to-end system: streaming environmental data → H3 spatial tiling → modular ML inference → WebSocket/REST → interactive deck.gl map with risk zones and wind-driven drift.

See **INSTALLATION.md** for setup. Short version: `uvicorn main:app --port 8000` in `backend/`, `npm install && npm run dev` in `frontend/`.

## Data flow

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
│   │   ├── core/config.py          FEATURES, TARGETS, PLACES, env settings
│   │   ├── ingestion/              simulator.py (mock stream) · base.py (RawSource contract) · real_feed_stub.py
│   │   ├── fusion/grid.py          H3 lattice, chunks, neighbours, lookup, GeoJSON
│   │   ├── models/                 base.py · mock.py · onnx_runner.py · torch_runner.py · registry.py
│   │   ├── services/               engine.py (pipeline) · advection.py · tracking.py · scoring.py
│   │   └── api/                    routes.py (REST) · ws.py (WebSocket)
│   ├── scripts/make_dummy_onnx.py
│   └── tests/test_pipeline.py
└── frontend/
    ├── package.json · tsconfig.json · tailwind.config.js · next.config.mjs
    └── src/
        ├── app/                    layout.tsx · page.tsx · globals.css
        ├── components/             MapViewer · ControlPanel · HazardLegend · CellTelemetry · ETACountdown
        ├── hooks/                  useNowcastStream (WS) · useWindParticles (animated wind field)
        └── lib/                    types · api · colors · metrics
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/config` | Domain, feature and target schema, places, horizons, model info |
| `GET /api/grid` | Static GeoJSON hex polygons (`i`, `id`, `chunk`, `lat`, `lon`) |
| `GET /api/snapshot?horizon=0..360` | GeoJSON with `risk`, 4 targets, `wind_u`, `wind_v`, `wind_speed_ms`, `wind_dir_deg` |
| `POST /api/ingest` | `{"observations":[{"lat":22.57,"lon":88.36,"values":{"dbz":60}}],"ttl_ticks":5}` overrides simulated values |
| `WS /ws/stream` | Server pushes a frame per tick. Client sends `{"horizon": 60}` to change lead time. |

Frame cell format (columnar per cell, index-aligned with `/api/grid`): `r` risk, `t` `[lightning, hail, downburst, cloudburst]`, `w` `[u, v]` m/s, `x` raw features in `config.features` order.

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
