"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ControlPanel from "@/components/ControlPanel";
import ETACountdown from "@/components/ETACountdown";
import HazardLegend from "@/components/HazardLegend";
import CellTelemetry from "@/components/CellTelemetry";
import RiskDrivers from "@/components/RiskDrivers";
import { useNowcastStream } from "@/hooks/useNowcastStream";
import { API_URL, getJson } from "@/lib/api";
import { fitView } from "@/lib/viewport";
import type {
  AppConfig, ColorMode, GridCell, JoinedCell, LayerToggles, MetricKey, PointInfo, ViewTarget,
} from "@/lib/types";

const MapViewer = dynamic(() => import("@/components/MapViewer"), { ssr: false });

export default function Page() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [grid, setGrid] = useState<GridCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("risk");
  const [horizon, setHorizon] = useState(0);
  const [dark, setDark] = useState(true);
  const [selectedStorm, setSelectedStorm] = useState<number | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>("zones");
  const [point, setPoint] = useState<PointInfo | null>(null);
  const [viewTarget, setViewTarget] = useState<ViewTarget | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [layers, setLayers] = useState<LayerToggles>({
    hex: true, heat: false, particles: true, arrows: true, storms: true, places: true,
  });
  const switching = useRef(false);
  const { frame, status } = useNowcastStream(horizon);

  const flash = useCallback((m: string) => {
    setNotice(m);
    setTimeout(() => setNotice((n) => (n === m ? null : n)), 4500);
  }, []);

  /** Fetch config + hex geometry for whatever region the server is showing right now. */
  const loadRegion = useCallback(async (fit = true) => {
    for (let attempt = 0; attempt < 3; attempt++) {
      const [cfg, gj] = await Promise.all([getJson<AppConfig>("/api/config"), getJson<any>("/api/grid")]);
      if (cfg.region_id !== gj.region_id) continue; // region changed mid-fetch: retry
      setGrid(gj.features.map((f: any): GridCell => ({
        i: f.properties.i, id: f.properties.id, chunk: f.properties.chunk,
        polygon: f.geometry.coordinates[0], centroid: [f.properties.lon, f.properties.lat],
      })));
      setConfig(cfg);
      if (fit) setViewTarget({ ...fitView(cfg.bbox, window.innerWidth, window.innerHeight), nonce: Date.now() });
      return cfg;
    }
    throw new Error("Region kept changing while loading");
  }, []);

  useEffect(() => {
    loadRegion().then(() => flash("Click anywhere on the map to see that area.")).catch(() =>
      setError(`Cannot reach the API at ${API_URL}. Start the backend (uvicorn main:app --port 8000) and reload.`));
  }, [loadRegion, flash]);

  // another viewer (or a click here) switched the server's region: reload geometry
  useEffect(() => {
    if (!frame || !config || switching.current || frame.region_id === config.region_id) return;
    switching.current = true;
    setPoint(null);
    loadRegion().catch(() => {}).finally(() => { switching.current = false; });
  }, [frame?.region_id, config?.region_id, loadRegion]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Click a spot (or use my location): show its info; load a new region if it is outside the current box. */
  const pick = useCallback(async (lat: number, lon: number, fly = false) => {
    if (busy) return;
    setBusy(true);
    try {
      let info = await getJson<PointInfo>(`/api/point?lat=${lat}&lon=${lon}`);
      if (!info.in_domain) {
        if (!info.in_india) { flash("That spot is outside India coverage."); return; }
        flash(`Loading storm data near ${info.nearest.name}…`);
        switching.current = true;
        try {
          await getJson("/api/region", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lat, lon }),
          });
          await loadRegion();
        } finally { switching.current = false; }
        info = await getJson<PointInfo>(`/api/point?lat=${lat}&lon=${lon}`);
      } else if (fly) {
        setViewTarget({ lon, lat, zoom: 9, nonce: Date.now() });
      }
      setPoint(info);
    } catch {
      flash("Could not reach the API. Is the backend running?");
    } finally {
      setBusy(false);
    }
  }, [busy, flash, loadRegion]);

  const locate = useCallback(() => {
    if (!navigator.geolocation) { flash("This browser does not support location."); return; }
    flash("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => pick(p.coords.latitude, p.coords.longitude, true),
      () => flash("Location was blocked or unavailable. Allow location access and try again."),
      { timeout: 10000 },
    );
  }, [pick, flash]);

  // keep the open spot's outlook fresh (every 3rd frame)
  const refreshKey = frame ? Math.floor(frame.tick / 3) : 0;
  useEffect(() => {
    if (!point || !point.in_domain || !config || point.region_id !== config.region_id) return;
    let live = true;
    getJson<PointInfo>(`/api/point?lat=${point.lat}&lon=${point.lon}`)
      .then((p) => { if (live && p.region_id === config.region_id) setPoint(p); }).catch(() => {});
    return () => { live = false; };
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const matched = !!(grid && frame && config && frame.region_id === config.region_id && frame.cells.length === grid.length);
  const cellsNow = useMemo<JoinedCell[] | null>(
    () => (matched ? grid!.map((g, i) => ({ ...g, ...frame!.cells[i] })) : null), [matched, grid, frame]);
  const lastCells = useRef<JoinedCell[] | null>(null);
  if (cellsNow) lastCells.current = cellsNow;
  const cells = cellsNow ?? lastCells.current; // keep the map on screen during a region switch

  if (error) {
    return <main className="h-screen grid place-items-center p-6 text-center"><p className="max-w-md text-slate-300">{error}</p></main>;
  }
  if (!config || !cells || !frame || !viewTarget) {
    return <main className="h-screen grid place-items-center text-slate-400">Loading the first forecast frame…</main>;
  }

  const selectedCell = matched && point && point.cell !== null && point.region_id === config.region_id ? cells[point.cell] : null;

  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <MapViewer
        config={config} cells={cells} storms={matched ? frame.storms : []} tick={frame.tick} horizon={horizon}
        metric={metric} layers={layers} dark={dark} selected={selectedCell ? selectedCell.i : null} onSelect={() => {}}
        colorMode={colorMode} selectedStorm={selectedStorm} onSelectStorm={setSelectedStorm}
        viewTarget={viewTarget} pin={point ? { lat: point.lat, lon: point.lon } : null} onPick={(la, lo) => pick(la, lo)}
      />
      {notice && (
        <div role="status" className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-slate-900/90 px-4 py-2 text-xs text-slate-100 border border-white/15">
          {notice}
        </div>
      )}
      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3 gap-3">
        <div className="flex justify-between items-start gap-3">
          <div className="pointer-events-auto">
            <ControlPanel {...{ config, frame, status, metric, setMetric, horizon, setHorizon, layers, setLayers, dark, setDark, colorMode, setColorMode, busy }} onLocate={locate} />
          </div>
          <div className="pointer-events-auto flex flex-col items-end gap-3 max-h-[calc(100vh-1.5rem)] overflow-auto">
            <ETACountdown frame={frame} config={config} />
            <RiskDrivers storms={matched ? frame.storms : []} config={config} selectedId={selectedStorm} onSelect={setSelectedStorm} />
            {selectedCell && (
              <CellTelemetry cell={selectedCell} config={config} frame={frame} point={point} onClose={() => setPoint(null)} />
            )}
          </div>
        </div>
        <div className="pointer-events-auto self-start"><HazardLegend metric={metric} config={config} colorMode={colorMode} cells={cells} /></div>
      </div>
    </main>
  );
}