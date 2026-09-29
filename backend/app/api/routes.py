from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

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
