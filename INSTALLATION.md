# Installation & run guide

Two processes: a **FastAPI backend** (port 8000) and a **Next.js frontend** (port 3000).
No API keys are needed. The basemap uses free CARTO styles; the data is simulated.

## 0. Prerequisites

| Tool | Version |
| --- | --- |
| Python | 3.10 or newer (tested on 3.12) |
| Node.js | 18.17 or newer (tested on 20) |
| A browser with WebGL2 | Chrome, Edge, Firefox, Safari 15+ |

## 1. Unzip

```bash
unzip convective-nowcasting.zip
cd convective-nowcasting
```

## 2. Backend (terminal 1)

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Windows (PowerShell)**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

You should see: `Engine up: 1506 cells, 46 chunks, model=mock-convective-heuristic`.

Check it:
* http://localhost:8000/api/health
* http://localhost:8000/docs (interactive API docs)
* http://localhost:8000/api/snapshot?horizon=60 (GeoJSON with risk + wind)

Run the tests (optional): `python -m pytest -q`

## 3. Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. The map loads after the first frame arrives (about 1 second).

If the backend is not on `localhost:8000`, copy `.env.local.example` to `.env.local` and edit `NEXT_PUBLIC_API_URL`.

## 4. What you should see

* Hex cells coloured white/blue (low), yellow/orange (moderate), red/magenta (severe), plus a soft heat glow.
* White particle streaks flowing with the live wind field; arrows showing where each hot cell is heading.
* Drag the **Forecast lead time** slider to +6 h. Risk zones slide downwind, spread, and weaken. The white lines show the drift.
* Hover a cell for a tooltip; click it for the full telemetry panel (model outputs, raw inputs, chunk, inference time).
* Top-right: arrival countdowns, then the **Storm digital twin** card (stage, risk history, confidence, end-of-life estimate) and the "why risk is changing" drivers.
* Bottom-right: **Sensor reliability**. Open *Try breaking a sensor*, press *Radar outage*, and watch data quality and confidence change.
* Left panel: the bar under *Forecast lead time* shows which forecast method dominates at that lead time.

The simulation runs about 1 simulated minute per real second, so storms visibly cross the map in a few minutes.

## 5. Configuration (environment variables for the backend)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BBOX` | `87.0,21.8,89.6,23.8` | `min_lon,min_lat,max_lon,max_lat` of the domain |
| `H3_RES` | `6` | Cell size. 6 is about 3 km edge (about 1,500 cells here). 7 is about 1.2 km (about 10,000 cells). |
| `CHUNK_RES` | `4` | Parent H3 level used as the unit of parallel inference (must be < `H3_RES`) |
| `TICK_SECONDS` | `2.0` | Real seconds between frames |
| `SIM_MINUTES_PER_TICK` | `2.0` | Simulated minutes advanced per frame |
| `MODEL_PATH` | unset | Path to a `.onnx` or TorchScript `.pt` file. Unset means the mock model. |
| `FAULT_RATE` | `0.006` | Chance per sensor source per tick of a random fault (outage, blind spot, noise). `0` disables random faults. |
| `N_MEMBERS` | `12` | Ensemble size for confidence ranges |
| `EXPLAIN_LAG_TICKS` | `5` | Window for the "why did risk change" comparison |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed browser origins |
| `SEED` | `42` | Simulator seed |

Example: `H3_RES=7 uvicorn main:app --port 8000`. Frames get about 7 times larger, so use res 7 on a smaller `BBOX`.

## 6. Troubleshooting

* **"Cannot reach the API"**: the backend is not running, or `NEXT_PUBLIC_API_URL` is wrong.
* **Blank grey map, no tiles**: the basemap needs internet access to `basemaps.cartocdn.com`. The hex layers still render offline.
* **`pip install h3` fails**: use Python 3.10 or newer and upgrade pip (`pip install -U pip`). Wheels exist for all major platforms.
* **Port already in use**: change `--port` (backend) or `npm run dev -- -p 3001` (frontend), then set `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL` to match.
* **Laggy particles**: lower `COUNT` in `frontend/src/hooks/useWindParticles.ts`.