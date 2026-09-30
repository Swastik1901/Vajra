"""Central configuration: feature schema, prediction targets, places, runtime settings."""
from __future__ import annotations

import os
from dataclasses import dataclass

# ---- Model input schema (order matters: this is the column order fed to ANY model) ----
FEATURES: list[str] = [
    "dbz",          # radar reflectivity (dBZ)                      <- DWR
    "vil",          # vertically integrated liquid (kg/m2)          <- DWR
    "cth_k",        # cloud-top brightness temperature (K)          <- INSAT TIR1
    "cooling_k15",  # cloud-top cooling rate (K / 15 min)           <- INSAT TIR1/WV
    "cape",         # convective available potential energy (J/kg) <- NWP / sounding
    "wind_u",       # low-level wind, eastward (m/s)                <- DWR velocity / analysis
    "wind_v",       # low-level wind, northward (m/s)
    "lightning",    # recent strike pulses per cell                 <- lightning network
    "humidity",     # low-level relative humidity (%)
]

# ---- Model output schema (4 targets) ; lo/hi normalise each into 0..1 for the composite risk ----
TARGETS: list[dict] = [
    {"key": "lightning",  "label": "Lightning strike density", "unit": "strikes/km²/hr", "lo": 0.0,  "hi": 70.0},
    {"key": "hail",       "label": "Hail probability",         "unit": "%",              "lo": 0.0,  "hi": 100.0},
    {"key": "downburst",  "label": "Downburst gust",           "unit": "km/h",           "lo": 40.0, "hi": 150.0},
    {"key": "cloudburst", "label": "Cloudburst risk",          "unit": "%",              "lo": 0.0,  "hi": 100.0},
]

# Size of the box loaded when the user clicks a new region (degrees lon x lat)
REGION_SPAN = (2.6, 2.0)

# Warning zones on the 0..1 combined-risk scale. `min` = lower bound of the zone (ascending).
ZONES: list[dict] = [
    {"key": "low",        "label": "Blue · Low",        "color": [59, 130, 246], "min": 0.00, "advice": "No significant convection"},
    {"key": "developing", "label": "Green · Developing", "color": [34, 197, 94],  "min": 0.15, "advice": "Isolated cells forming; monitor"},
    {"key": "watch",      "label": "Yellow · Watch",     "color": [250, 204, 21], "min": 0.30, "advice": "Thunderstorms possible; be alert"},
    {"key": "warning",    "label": "Orange · Warning",   "color": [249, 115, 22], "min": 0.50, "advice": "Intense cell; lightning, heavy rain. Stay indoors"},
    {"key": "severe",     "label": "Red · Severe",       "color": [239, 68, 68],  "min": 0.70, "advice": "Hail, damaging gusts or flash-flood risk"},
    {"key": "extreme",    "label": "Purple · Extreme",   "color": [192, 38, 211], "min": 0.88, "advice": "Life-threatening; take shelter now"},
]

HORIZONS_MIN = list(range(0, 361, 15))


@dataclass(frozen=True)
class Settings:
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat
    h3_res: int
    chunk_res: int
    tick_seconds: float
    sim_minutes_per_tick: float
    model_path: str | None
    cors_origins: list[str]
    seed: int
    explain_lag_ticks: int

    @property
    def time_lapse(self) -> float:
        """Simulated seconds per wall-clock second."""
        return self.sim_minutes_per_tick * 60.0 / self.tick_seconds


def load_settings() -> Settings:
    bbox = tuple(float(x) for x in os.getenv("BBOX", "87.0,21.8,89.6,23.8").split(","))
    s = Settings(
        bbox=bbox,  # type: ignore[arg-type]
        h3_res=int(os.getenv("H3_RES", "6")),
        chunk_res=int(os.getenv("CHUNK_RES", "4")),
        tick_seconds=float(os.getenv("TICK_SECONDS", "2.0")),
        sim_minutes_per_tick=float(os.getenv("SIM_MINUTES_PER_TICK", "2.0")),
        model_path=os.getenv("MODEL_PATH") or None,
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
        seed=int(os.getenv("SEED", "42")),
        explain_lag_ticks=int(os.getenv("EXPLAIN_LAG_TICKS", "5")),
    )
    if s.chunk_res >= s.h3_res:
        raise ValueError("CHUNK_RES must be coarser (smaller) than H3_RES")
    return s


settings = load_settings()