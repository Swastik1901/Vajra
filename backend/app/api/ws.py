from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/stream")
async def stream(ws: WebSocket):
    """Server pushes a frame every tick. Client may send {"horizon": <minutes 0..360>} at any time."""
    await ws.accept()
    engine = ws.app.state.engine
    q = engine.subscribe()
    state = {"horizon": 0}
    engine.notify(q, engine.tick_id)  # immediate first frame

    async def reader():
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and "horizon" in msg:
                state["horizon"] = max(0, min(360, int(msg["horizon"])))
                engine.notify(q, engine.tick_id)

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            getter = asyncio.ensure_future(q.get())
            done, _ = await asyncio.wait({getter, reader_task}, return_when=asyncio.FIRST_COMPLETED)
            if reader_task in done:
                getter.cancel()
                reader_task.result()  # raises WebSocketDisconnect
                break
            await ws.send_text(await asyncio.to_thread(engine.frame_json, state["horizon"]))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        reader_task.cancel()
        engine.unsubscribe(q)
