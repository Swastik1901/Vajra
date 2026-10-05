from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..core.cities import in_india
from ..core.config import FEATURES

router = APIRouter(prefix="/api")


def _engine(request: Request):
    return request.app.state.engine


@router.get("/health")
def health(request: Request):
    e = _engine(request)
    return {"status": "ok", "tick": e.tick_id, "model": e.model.name, "cells": e.grid.n}


@router.get("/config")
def config(request: Request):
    return _engine(request).config_payload()


@router.get("/grid")
def grid(request: Request):
    """Static hex geometry. Fetched once; per-tick frames only carry values (keeps payloads small)."""
    return _engine(request).grid_geojson


@router.post("/pause")
def pause(request: Request):
    """Freeze the simulation (good for explaining one screen). The lead-time slider keeps working."""
    e = _engine(request)
    e.set_paused(True)
    e.broadcast()
    return {"paused": True}


@router.post("/resume")
def resume(request: Request):
    e = _engine(request)
    e.set_paused(False)
    e.broadcast()
    return {"paused": False}


@router.get("/sensors")
def sensors(request: Request):
    """Health of each observation source and a summary of how the fused inputs were obtained."""
    return _engine(request).sensors_payload()


class FaultRequest(BaseModel):
    source: str
    mode: str = Field(..., description="outage | partial | noisy")
    duration_ticks: int = Field(30, ge=1, le=300)


@router.post("/faults")
def inject_fault(body: FaultRequest, request: Request):
    """Demo/testing: break a sensor source on purpose to watch the fusion layer cope."""
    e = _engine(request)
    try:
        e.inject_fault(body.source, body.mode, body.duration_ticks)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True}


@router.delete("/faults")
def clear_faults(request: Request):
    _engine(request).clear_faults()
    return {"ok": True}


@router.get("/point")
def point(request: Request, lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """Click-a-spot summary: nearest city, risk now, 6-hour outlook, storm arrival at that point."""
    return _engine(request).point_info(lat, lon)


class RegionRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


@router.post("/region")
async def set_region(body: RegionRequest, request: Request):
    """Re-centre the monitored box on a clicked spot (India only). Shared by all connected viewers."""
    if not in_india(body.lat, body.lon):
        raise HTTPException(422, "That spot is outside India coverage.")
    e = _engine(request)
    await asyncio.to_thread(e.switch_region, body.lat, body.lon)
    e.broadcast()
    return e.config_payload()


@router.get("/explain/cell/{i}")
def explain_cell(i: int, request: Request):
    """Drivers of the recent risk change for one cell (reflectivity, lightning, cloud-top, wind)."""
    e = _engine(request)
    if not 0 <= i < e.grid.n:
        raise HTTPException(404, "cell index out of range")
    return e.explain_cell(i)


@router.get("/snapshot")
def snapshot(request: Request, horizon: int = Query(0, ge=0, le=360)):
    """Polling alternative to the WebSocket: GeoJSON with risk scores + wind vectors."""
    return _engine(request).snapshot_geojson(horizon)


class Observation(BaseModel):
    lat: float
    lon: float
    values: dict[str, float] = Field(..., description=f"any subset of {FEATURES}")


class IngestRequest(BaseModel):
    observations: list[Observation]
    ttl_ticks: int = Field(5, ge=1, le=100)


@router.post("/ingest")
def ingest(body: IngestRequest, request: Request):
    """Push real point observations; they override the simulated field for `ttl_ticks` ticks."""
    for o in body.observations:
        bad = [k for k in o.values if k not in FEATURES]
        if bad:
            raise HTTPException(422, f"unknown feature(s) {bad}; allowed: {FEATURES}")
    applied = _engine(request).ingest([o.model_dump() for o in body.observations], body.ttl_ticks)
    return {"received": len(body.observations), "applied": applied}