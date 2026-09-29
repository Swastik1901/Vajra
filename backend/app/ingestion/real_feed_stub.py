"""Where real feeds plug in. Implement `RawSource` and swap it in `services/engine.py`.

Suggested production wiring (see README):
  DWR  (IMD NetCDF/radial)  --Py-ART-->  Cartesian reflectivity/velocity  --\
  INSAT-3D/3DR (HDF5)       --Xarray-->  TIR1/TIR2/WV, cooling rate         >-- Kafka topics -> this class
  Lightning network (JSON)  --------->  pulses -> per-cell counts         --/
Each consumer regrids to the H3 lattice with `HexGrid.lookup` (point data) or area-weighted resampling (rasters).
"""
from __future__ import annotations

import numpy as np


class KafkaRawSource:
    def __init__(self, bootstrap_servers: str, topics: list[str]):
        raise NotImplementedError("Wire aiokafka / confluent-kafka consumers here.")

    def step(self, dt_min: float) -> None: ...

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]: ...
