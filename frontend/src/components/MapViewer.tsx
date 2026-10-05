"use client";
import { useMemo } from "react";
import { Map as MapGL } from "react-map-gl/maplibre";
import {
  DeckGL, PathLayer, PolygonLayer, HeatmapLayer, IconLayer, LineLayer, ScatterplotLayer, TextLayer, TripsLayer, FlyToInterpolator,
} from "deck.gl";
import { HEAT_RANGE, riskColor, zoneColor } from "@/lib/colors";
import { isHazardMetric, metricValue, METRICS, targetIndex } from "@/lib/metrics";
import { TRAIL_TIMESTAMPS, useWindParticles, type Trail } from "@/hooks/useWindParticles";
import type { AppConfig, ColorMode, JoinedCell, LayerToggles, MetricKey, Storm, ViewTarget } from "@/lib/types";

const STYLE_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const STYLE_LIGHT = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json";

const ARROW_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><polygon points="32,4 52,36 38,36 38,60 26,60 26,36 12,36" fill="white"/></svg>';
const ARROW_ICON = {
  url: `data:image/svg+xml;utf8,${encodeURIComponent(ARROW_SVG)}`,
  width: 64, height: 64, anchorY: 32, mask: true,
};

interface Props {
  config: AppConfig;
  cells: JoinedCell[];
  storms: Storm[];
  tick: number;
  horizon: number;
  metric: MetricKey;
  layers: LayerToggles;
  dark: boolean;
  selected: number | null;
  onSelect: (i: number | null) => void;
  colorMode: ColorMode;
  selectedStorm: number | null;
  onSelectStorm: (id: number | null) => void;
  viewTarget: ViewTarget;
  pin: { lat: number; lon: number } | null;
  onPick: (lat: number, lon: number) => void;
}

export default function MapViewer(p: Props) {
  const { config, cells, storms, tick, horizon, metric, layers, dark, selected, colorMode, selectedStorm, pin, viewTarget } = p;
  const trails = useWindParticles(cells, config, layers.particles);

  // changing viewTarget (region switch, "my location") makes deck.gl fly there
  const initialViewState = useMemo(() => ({
    longitude: viewTarget.lon, latitude: viewTarget.lat, zoom: viewTarget.zoom, pitch: 0, bearing: 0,
    transitionDuration: 1400, transitionInterpolator: new FlyToInterpolator(), nonce: viewTarget.nonce,
  }), [viewTarget]);

  const val = (c: JoinedCell) => metricValue(c, metric, config);
  const useZones = colorMode === "zones" && (metric === "risk" || isHazardMetric(metric));

  // storm digital twins: projected positions with a widening uncertainty cone
  const rings = useMemo(
    () => storms.flatMap((s) => (s.twin?.track_future ?? []).filter((q) => q.m > 0).map((q) => ({ ...q, risk: s.risk, id: s.id }))),
    [storms]);
  const hourMarks = useMemo(() => rings.filter((q) => [60, 120, 240, 360].includes(q.m)), [rings]);

  // where storm `s` will be `minutes` from now, read off its projected track
  const stormAt = (s: Storm, minutes: number): [number, number] => {
    const f = s.twin?.track_future ?? [];
    if (f.length < 2) return [s.lon, s.lat];
    let i = 1;
    while (i < f.length - 1 && f[i].m < minutes) i++;
    const a = f[i - 1], b = f[i];
    const t = b.m === a.m ? 0 : Math.max(0, Math.min(1, (minutes - a.m) / (b.m - a.m)));
    return [a.lon + (b.lon - a.lon) * t, a.lat + (b.lat - a.lat) * t];
  };

  const layerList = [
    layers.heat && new HeatmapLayer<JoinedCell>({
      id: "heat", data: cells, getPosition: (c) => c.centroid, getWeight: (c) => (val(c) > 0.08 ? val(c) : 0),
      radiusPixels: 55, intensity: 1.6, threshold: 0.04, colorRange: HEAT_RANGE, opacity: 0.8,
      updateTriggers: { getWeight: [metric, tick] },
    }),
    layers.hex && new PolygonLayer<JoinedCell>({
      id: "hex", data: cells, getPolygon: (c) => c.polygon, getFillColor: (c) => (useZones ? zoneColor(val(c), config.zones) : riskColor(val(c))),
      stroked: true, getLineColor: [255, 255, 255, 22], lineWidthMinPixels: 0.5, pickable: true,
      autoHighlight: true, highlightColor: [255, 255, 255, 80],
      updateTriggers: { getFillColor: [metric, tick, colorMode, useZones] },
    }),
    selected !== null && cells[selected] && new PolygonLayer<JoinedCell>({
      id: "selected", data: [cells[selected]], getPolygon: (c) => c.polygon, filled: false,
      stroked: true, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 3,
    }),
    layers.particles && new TripsLayer<Trail>({
      id: "wind", data: trails, getPath: (d) => d.path, getTimestamps: () => TRAIL_TIMESTAMPS,
      getColor: (d) => (d.speed > 16 ? [255, 120, 90] : d.speed > 11 ? [255, 210, 140] : [190, 225, 255]),
      currentTime: TRAIL_TIMESTAMPS.length - 1, trailLength: TRAIL_TIMESTAMPS.length - 1, fadeTrail: true,
      widthMinPixels: 1.6, capRounded: true, jointRounded: true, opacity: 0.8,
    }),
    layers.arrows && horizon > 0 && new LineLayer<Storm>({
      id: "drift", data: storms, getSourcePosition: (s) => [s.lon, s.lat],
      getTargetPosition: (s) => stormAt(s, horizon), getColor: [255, 255, 255, 190], getWidth: 2, widthUnits: "pixels",
      updateTriggers: { getTargetPosition: [horizon, tick] },
    }),
    layers.arrows && new IconLayer<Storm>({
      id: "arrows", data: storms, getPosition: (s) => [s.lon, s.lat], getIcon: () => ARROW_ICON,
      getAngle: (s) => -s.bearing_deg, getSize: 30, sizeUnits: "pixels", getPixelOffset: [0, 0],
      getColor: [255, 255, 255, 235], updateTriggers: { getAngle: [tick] },
    }),
    layers.tracks && new ScatterplotLayer<(typeof rings)[number]>({
      id: "track-cone", data: rings, getPosition: (d) => [d.lon, d.lat], getRadius: (d) => d.radius_km * 1000,
      filled: true, getFillColor: (d) => zoneColor(d.risk, config.zones, Math.max(14, 60 - d.m / 7)),
      stroked: true, getLineColor: [255, 255, 255, 50], lineWidthMinPixels: 1,
    }),
    layers.tracks && new PathLayer<Storm>({
      id: "track-future", data: storms, getPath: (s) => (s.twin?.track_future ?? []).map((q): [number, number] => [q.lon, q.lat]),
      getColor: [255, 255, 255, 170], widthMinPixels: 2, capRounded: true, jointRounded: true,
    }),
    layers.tracks && new PathLayer<Storm>({
      id: "track-past", data: storms, getPath: (s) => s.twin?.track_past ?? [],
      getColor: (s) => zoneColor(s.risk, config.zones, 235), widthMinPixels: 3.5, capRounded: true, jointRounded: true,
      updateTriggers: { getColor: [tick] },
    }),
    layers.tracks && new TextLayer<(typeof rings)[number]>({
      id: "track-labels", data: hourMarks, getPosition: (d) => [d.lon, d.lat], getText: (d) => `+${d.m / 60}h`,
      getSize: 11, getColor: [255, 255, 255, 230], getPixelOffset: [0, -10], fontSettings: { sdf: true },
      outlineWidth: 3, outlineColor: [11, 18, 32, 255],
    }),
    layers.storms && new ScatterplotLayer<Storm>({
      id: "storms", data: storms, getPosition: (s) => [s.lon, s.lat], getRadius: (s) => s.radius_km * 1000,
      filled: false, stroked: true, pickable: true,
      getLineColor: (s) => zoneColor(s.risk, config.zones, 255),
      getLineWidth: (s) => (s.id === selectedStorm ? 5 : 2.5), lineWidthUnits: "pixels",
      updateTriggers: { getLineColor: [tick], getLineWidth: [selectedStorm] },
    }),
    layers.storms && new TextLayer<Storm>({
      id: "storm-labels", data: storms, getPosition: (s) => [s.lon, s.lat],
      getText: (s) => `#${s.id} · ${Math.round(s.speed_kmh)} km/h`,
      getSize: 12, getColor: [255, 255, 255, 255], getPixelOffset: [0, -16],
      background: true, getBackgroundColor: [15, 23, 42, 200], backgroundPadding: [4, 2],
    }),
    layers.places && new ScatterplotLayer({
      id: "places", data: config.places, getPosition: (d: any) => [d.lon, d.lat], getRadius: 4,
      radiusUnits: "pixels", getFillColor: [255, 255, 255, 255], getLineColor: [15, 23, 42, 255],
      stroked: true, lineWidthMinPixels: 1.5,
    }),
    layers.places && new TextLayer({
      id: "place-labels", data: config.places, getPosition: (d: any) => [d.lon, d.lat], getText: (d: any) => d.name,
      getSize: 12, getColor: dark ? [226, 232, 240, 255] : [15, 23, 42, 255], getPixelOffset: [0, 14],
      outlineWidth: 3, outlineColor: dark ? [11, 18, 32, 255] : [255, 255, 255, 255], fontSettings: { sdf: true },
    }),
    pin && new ScatterplotLayer({
      id: "pin", data: [pin], getPosition: (d: any) => [d.lon, d.lat], getRadius: 9, radiusUnits: "pixels",
      getFillColor: [255, 255, 255, 255], stroked: true, getLineColor: [15, 23, 42, 255], lineWidthMinPixels: 3,
    }),
  ].filter(Boolean);

  const metricLabel = METRICS.find((m) => m.key === metric)!.label;

  return (
    <DeckGL
      initialViewState={initialViewState}
      controller
      onClick={(info: any) => {
        if (info.layer?.id === "storms" && info.object) p.onSelectStorm((info.object as Storm).id);
        if (info.coordinate) p.onPick(info.coordinate[1], info.coordinate[0]);
      }}
      layers={layerList as any}
      getTooltip={({ object, layer }: any) => {
        if (!object || layer?.id !== "hex") return null;
        const c = object as JoinedCell;
        const rows = config.targets
          .map((t, i) => `${t.label}: <b>${c.t[i].toFixed(0)}</b> ${t.unit}`)
          .join("<br/>");
        return {
          html: `<div class="deck-tooltip"><b>${metricLabel}: ${(val(c) * 100).toFixed(0)}%</b><br/>${rows}<br/>Risk ${(c.r * 100).toFixed(0)}% (${(c.lo * 100).toFixed(0)}–${(c.hi * 100).toFixed(0)}%), confidence ${(c.c * 100).toFixed(0)}%<br/>Click for details</div>`,
          style: { background: "rgba(15,23,42,.94)", color: "#e2e8f0", fontSize: "12px", borderRadius: "8px", padding: "8px 10px" },
        };
      }}
    >
      <MapGL mapStyle={dark ? STYLE_DARK : STYLE_LIGHT} reuseMaps />
    </DeckGL>
  );
}

export { targetIndex };