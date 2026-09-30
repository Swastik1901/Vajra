from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes, ws
from app.core.config import settings
from app.services.engine import NowcastEngine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = NowcastEngine(settings)
    await asyncio.to_thread(engine.compute_tick)   # first frame ready before we serve
    app.state.engine = engine
    task = asyncio.create_task(engine.run())
    logging.info("Engine up: %d cells, %d chunks, model=%s", engine.grid.n, len(engine.grid.chunks), engine.model.name)
    yield
    task.cancel()


app = FastAPI(title="Convective Nowcasting API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(routes.router)
app.include_router(ws.router)