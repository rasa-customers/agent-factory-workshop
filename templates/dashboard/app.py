"""Dashboard server — the fixed contract. The factory builds the UI in static/.

Contract:
  POST /api/state   {"panel": "flight"|"weather"|"meeting"|"verdict", "data": {...}}  → merges, returns full state
  GET  /api/state   → {"flight": {...}|null, "weather": ..., "meeting": ..., "verdict": ...}
  GET  /api/events  → Server-Sent Events; a `state` event with the full state on connect and after every change
  POST /api/reset   → clears state
  GET  /            → static/index.html

Run:  uvicorn app:app --port 8600
"""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PANELS = ("flight", "weather", "meeting", "verdict")
STATIC = Path(__file__).parent / "static"


class Update(BaseModel):
    panel: Literal["flight", "weather", "meeting", "verdict"]
    data: dict[str, Any]


class Hub:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {p: None for p in PANELS}
        self.queues: set[asyncio.Queue[str]] = set()

    def snapshot(self) -> str:
        return json.dumps(self.state)

    async def publish(self) -> None:
        msg = self.snapshot()
        for q in list(self.queues):
            q.put_nowait(msg)

    async def subscribe(self) -> AsyncIterator[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self.queues.add(q)
        try:
            yield self.snapshot()
            while True:
                yield await q.get()
        finally:
            self.queues.discard(q)


hub = Hub()
app = FastAPI(title="Flight dashboard")


async def set_panel(panel: str, data: dict[str, Any]) -> dict[str, Any]:
    hub.state[panel] = {**(hub.state[panel] or {}), **data}
    await hub.publish()
    return hub.state


@app.post("/api/state")
async def post_state(update: Update) -> dict[str, Any]:
    return await set_panel(update.panel, update.data)


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return hub.state


@app.post("/api/reset")
async def reset() -> dict[str, Any]:
    hub.state = {p: None for p in PANELS}
    await hub.publish()
    return hub.state


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        async for msg in hub.subscribe():
            yield f"event: state\ndata: {msg}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
