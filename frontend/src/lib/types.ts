export interface TargetSpec { key: string; label: string; unit: string; lo: number; hi: number }
export interface Place { name: string; lat: number; lon: number }

export interface AppConfig {
  bbox: [number, number, number, number];
  h3_res: number; chunk_res: number; n_cells: number; n_chunks: number;
  cell_spacing_deg: number;
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
export interface FrameCell { r: number; t: number[]; w: [number, number]; x: number[] }

export interface Storm {
  id: number; lat: number; lon: number; radius_km: number; risk: number;
  u: number; v: number; speed_kmh: number; bearing_deg: number; hazard: string; n_cells: number;
}
export interface Eta { place: string; storm_id: number; eta_min: number; hazard: string; risk: number }

export interface Frame {
  type: "frame"; tick: number; sim_time: string; horizon: number;
  model: { name: string; version: string };
  inference_ms: number; n_chunks: number;
  stats: { n_cells: number; high_cells: number; mean_risk: number; max: number[] };
  storms: Storm[]; etas: Eta[]; cells: FrameCell[];
  receivedAt?: number;
}

export type JoinedCell = GridCell & FrameCell;
export type MetricKey = "risk" | "lightning" | "hail" | "downburst" | "cloudburst";
export interface LayerToggles {
  hex: boolean; heat: boolean; particles: boolean; arrows: boolean; storms: boolean; places: boolean;
}
