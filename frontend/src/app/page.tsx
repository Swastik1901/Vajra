"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import ControlPanel from "@/components/ControlPanel";
import ETACountdown from "@/components/ETACountdown";
import HazardLegend from "@/components/HazardLegend";
import CellTelemetry from "@/components/CellTelemetry";
import { useNowcastStream } from "@/hooks/useNowcastStream";
import { API_URL } from "@/lib/api";
import type { AppConfig, GridCell, JoinedCell, LayerToggles, MetricKey } from "@/lib/types";

const MapViewer = dynamic(() => import("@/components/MapViewer"), { ssr: false });

export default function Page() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [grid, setGrid] = useState<GridCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("risk");
  const [horizon, setHorizon] = useState(0);
  const [dark, setDark] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [layers, setLayers] = useState<LayerToggles>({
    hex: true, heat: true, particles: true, arrows: true, storms: true, places: true,
  });
  const { frame, status } = useNowcastStream(horizon);

  useEffect(() => {
    (async () => {
      try {
        const [cfg, gj] = await Promise.all([
          fetch(`${API_URL}/api/config`).then((r) => r.json()),
          fetch(`${API_URL}/api/grid`).then((r) => r.json()),
        ]);
        setConfig(cfg);
        setGrid(gj.features.map((f: any): GridCell => ({
          i: f.properties.i, id: f.properties.id, chunk: f.properties.chunk,
          polygon: f.geometry.coordinates[0], centroid: [f.properties.lon, f.properties.lat],
        })));
      } catch {
        setError(`Cannot reach the API at ${API_URL}. Start the backend (uvicorn main:app --port 8000) and reload.`);
      }
    })();
  }, []);

  const cells: JoinedCell[] | null = useMemo(() => {
    if (!grid || !frame || frame.cells.length !== grid.length) return null;
    return grid.map((g, i) => ({ ...g, ...frame.cells[i] }));
  }, [grid, frame]);

  if (error) {
    return <main className="h-screen grid place-items-center p-6 text-center"><p className="max-w-md text-slate-300">{error}</p></main>;
  }
  if (!config || !cells || !frame) {
    return <main className="h-screen grid place-items-center text-slate-400">Loading the first forecast frame…</main>;
  }

  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <MapViewer
        config={config} cells={cells} storms={frame.storms} tick={frame.tick} horizon={horizon}
        metric={metric} layers={layers} dark={dark} selected={selected} onSelect={setSelected}
      />
      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3 gap-3">
        <div className="flex justify-between items-start gap-3">
          <div className="pointer-events-auto">
            <ControlPanel {...{ config, frame, status, metric, setMetric, horizon, setHorizon, layers, setLayers, dark, setDark }} />
          </div>
          <div className="pointer-events-auto flex flex-col items-end gap-3">
            <ETACountdown frame={frame} config={config} />
            {selected !== null && cells[selected] && (
              <CellTelemetry cell={cells[selected]} config={config} frame={frame} onClose={() => setSelected(null)} />
            )}
          </div>
        </div>
        <div className="pointer-events-auto self-start"><HazardLegend metric={metric} config={config} /></div>
      </div>
    </main>
  );
}
