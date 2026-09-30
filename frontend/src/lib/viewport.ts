/** Pick a zoom level so the whole bbox fits in ~80% of the screen (Web-Mercator maths). */
export function fitView(bbox: [number, number, number, number], w = 1400, h = 800) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const lat = (minLat + maxLat) / 2;
  const lon = (minLon + maxLon) / 2;
  const lonSpan = maxLon - minLon;
  const latSpan = (maxLat - minLat) / Math.cos((lat * Math.PI) / 180);
  const zLon = Math.log2((0.8 * w * 360) / (512 * lonSpan));
  const zLat = Math.log2((0.8 * h * 360) / (512 * latSpan));
  return { lon, lat, zoom: Math.max(4, Math.min(10, Math.min(zLon, zLat))) };
}