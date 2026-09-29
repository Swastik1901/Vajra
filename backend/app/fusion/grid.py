"""Spatial chunking: H3 hex lattice over a bbox, hierarchical chunks, neighbour topology."""
from __future__ import annotations

import h3
import numpy as np


class HexGrid:
    """Fixed H3 lattice covering `bbox`.

    * level `res`       -> analysis cells (~3 km edge at res 6, ~1.2 km at res 7)
    * level `chunk_res` -> parent hexes = independent work units for parallel / distributed inference
    """

    def __init__(self, bbox: tuple[float, float, float, float], res: int, chunk_res: int):
        min_lon, min_lat, max_lon, max_lat = bbox
        self.bbox, self.res, self.chunk_res = bbox, res, chunk_res

        edge_km = h3.average_hexagon_edge_length(res, unit="km")
        step = edge_km / 111.0 * 0.7  # oversample so no hex is missed
        found: set[str] = set()
        for la in np.arange(min_lat, max_lat + step, step):
            for lo in np.arange(min_lon, max_lon + step, step):
                found.add(h3.latlng_to_cell(float(la), float(lo), res))

        cells, lats, lons = [], [], []
        for c in sorted(found):
            la, lo = h3.cell_to_latlng(c)
            if min_lat <= la <= max_lat and min_lon <= lo <= max_lon:
                cells.append(c); lats.append(la); lons.append(lo)

        self.cells: list[str] = cells
        self.lat = np.asarray(lats, dtype=np.float64)
        self.lon = np.asarray(lons, dtype=np.float64)
        self.n = len(cells)
        self.index = {c: i for i, c in enumerate(cells)}
        self.cell_area_km2 = h3.average_hexagon_area(res, unit="km^2")
        self.spacing_deg = float(np.sqrt(3) * edge_km / 111.0)  # centre-to-centre distance

        # hierarchical chunks (parent hex -> member indices)
        parents: dict[str, list[int]] = {}
        self.chunk_of: list[str] = []
        for i, c in enumerate(cells):
            p = h3.cell_to_parent(c, chunk_res)
            parents.setdefault(p, []).append(i)
            self.chunk_of.append(p)
        self.chunks: dict[str, np.ndarray] = {p: np.asarray(v, dtype=np.int64) for p, v in parents.items()}

        # neighbour topology (N, 6), -1 = outside domain
        nbr = np.full((self.n, 6), -1, dtype=np.int64)
        for i, c in enumerate(cells):
            k = 0
            for nb in h3.grid_disk(c, 1):
                if nb == c or k >= 6:
                    continue
                nbr[i, k] = self.index.get(nb, -1)
                k += 1
        self.nbr = nbr

    # ------------------------------------------------------------------ helpers
    def lookup(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Vectorised (lat, lon) -> cell index, -1 when outside the domain."""
        res, index = self.res, self.index
        return np.fromiter(
            (index.get(h3.latlng_to_cell(float(a), float(b), res), -1) if -90 <= a <= 90 else -1
             for a, b in zip(lat, lon)),
            dtype=np.int64, count=len(lat),
        )

    def neighbor_mean(self, a: np.ndarray) -> np.ndarray:
        """Mean of the valid 1-ring neighbours per cell. `a` is (N,) or (N,K)."""
        a2 = a if a.ndim == 2 else a[:, None]
        padded = np.vstack([a2, np.zeros((1, a2.shape[1]))])
        idx = np.where(self.nbr >= 0, self.nbr, self.n)
        valid = (self.nbr >= 0).astype(np.float64)
        s = (padded[idx] * valid[..., None]).sum(axis=1)
        out = s / np.maximum(valid.sum(axis=1), 1.0)[:, None]
        return out if a.ndim == 2 else out[:, 0]

    def to_geojson(self) -> dict:
        feats = []
        for i, c in enumerate(self.cells):
            ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(c)]
            ring.append(ring[0])
            feats.append({
                "type": "Feature",
                "id": i,
                "properties": {"i": i, "id": c, "chunk": self.chunk_of[i],
                               "lat": float(self.lat[i]), "lon": float(self.lon[i])},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            })
        return {"type": "FeatureCollection", "features": feats}
