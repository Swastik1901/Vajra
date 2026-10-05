export interface TargetSpec { key: string; label: string; unit: string; lo: number; hi: number }
export interface ZoneSpec { key: string; label: string; color: [number, number, number]; min: number; advice: string }
export interface Driver { key: string; text: string; detail: string }
export interface Why {
  direction: "up" | "down" | "steady";
  risk_before: number | null; risk_now: number; risk_delta: number; lag_min: number;
  drivers: Driver[];
}
export type ColorMode = "zones" | "gradient";
export interface Place { name: string; lat: number; lon: number }

export interface AppConfig {
  bbox: [number, number, number, number];
  calm: boolean;
  region_id: number; region_name: string;
  h3_res: number; chunk_res: number; n_cells: number; n_chunks: number;
  cell_spacing_deg: number; cell_area_km2: number;
  zones: ZoneSpec[]; explain_lag_min: number;
  features: string[];
  targets: TargetSpec[];
  places: Place[];
  horizons: number[];
  tick_seconds: number; sim_minutes_per_tick: number; time_lapse: number;
  model: { name: string; version: string };
}

/** Static geometry, fetched once from /api/grid */
export interface GridCell {
  i: number; id: string; chunk: string;
  polygon: [number, number][];
  centroid: [number, number];
}

/** Per-tick values, index-aligned with GridCell[]. r=risk, t=4 targets, w=[u,v] m/s, x=raw features */
export interface FrameCell {
  r: number; t: number[]; w: [number, number]; x: number[];
  lo: number; hi: number;   // 10th-90th percentile of risk (ensemble)
  c: number;                // confidence 0..1
  p: number;                // probability of Warning zone or worse
  q: number;                // input data quality 0..1
}

export interface Storm {
  id: number; lat: number; lon: number; radius_km: number; risk: number;
  u: number; v: number; speed_kmh: number; bearing_deg: number; hazard: string; n_cells: number;
  why: Why;
  lo: number; hi: number; conf: number; p_warning: number;
  peak_targets: number[];
  twin: Twin;
}
export type Stage = "initiating" | "intensifying" | "mature" | "weakening";
export interface TrackPoint { m: number; lat: number; lon: number; radius_km: number }
export interface Twin {
  stage: Stage; observed_min: number; trend_per_10min: number;
  eol_min: number | null; eol_basis: "trend" | "typical";
  track_past: [number, number][]; risk_hist: number[]; peak_risk: number; peak_targets: number[];
  track_future: TrackPoint[];
}
export interface EndedStorm { id: number; lifetime_min: number; peak_risk: number; ended_min_ago: number }
export interface SensorHealthItem {
  source: string; label: string; features: string[];
  status: "ok" | "noisy" | "outage" | "partial outage"; mode: string | null;
  remaining_ticks: number; availability_pct: number; noise_mult: number; cadence_min: number;
}
export interface FusionSummary { mean_quality: number; min_quality: number; mix: Record<string, number> }
export interface Strategy { horizon: number; weights: { extrapolation: number; lifecycle: number; environment: number } }
export interface Eta { place: string; storm_id: number; eta_min: number; hazard: string; risk: number }

export interface Frame {
  type: "frame"; tick: number; paused: boolean; calm: boolean; region_id: number; region_name: string; sim_time: string; horizon: number;
  model: { name: string; version: string };
  inference_ms: number; n_chunks: number;
  stats: { n_cells: number; high_cells: number; mean_risk: number; max: number[] };
  storms: Storm[]; etas: Eta[]; cells: FrameCell[];
  strategy: Strategy; sensors: SensorHealthItem[]; fusion: FusionSummary; twins_ended: EndedStorm[];
  receivedAt?: number;
}

export type JoinedCell = GridCell & FrameCell;
export type MetricKey = "risk" | "lightning" | "hail" | "downburst" | "cloudburst" | "uncertainty" | "quality";
export interface LayerToggles {
  hex: boolean; heat: boolean; particles: boolean; arrows: boolean; storms: boolean; places: boolean; tracks: boolean;
}

export interface ViewTarget { lon: number; lat: number; zoom: number; nonce: number }

export interface Nearest { name: string; distance_km: number; bearing: string }
export interface PointInfo {
  lat: number; lon: number; in_india: boolean; in_domain: boolean;
  region_id: number; region_name: string; nearest: Nearest; cell: number | null;
  now: { risk: number; targets: number[]; wind: [number, number] } | null;
  forecast: { minutes: number; risk: number; lo: number; hi: number; conf: number; p_warning: number; targets: number[] }[];
  quality?: { score: number; features: { name: string; value: number; reliability: number; source: string }[] };
  arrivals: { place: string; storm_id: number; eta_min: number; hazard: string; risk: number }[];
}