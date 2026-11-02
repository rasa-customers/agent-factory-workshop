"""The factory's front door: MCP tools for the foreman, plus a live activity page.

Builds take minutes and Mantle gives up on a tool call after ~10-30s, so every tool returns immediately.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse

from factory.jobs import KINDS, Job, JobStore
from workshop.env import export_settings

Runner = Callable[[Job], Awaitable[None]]
ACTIVITY_HTML = Path(__file__).with_name("activity.html")


def public_url() -> str:
    return os.environ.get("FACTORY_PUBLIC_URL", "http://localhost:8800").rstrip("/")


def build_server(store: JobStore, runner: Runner, *, port: int = 8800) -> FastMCP:
    mcp = FastMCP("factory", host="0.0.0.0", port=port)
    tasks: set[asyncio.Task] = set()

    async def _run(job: Job) -> None:
        try:
            await runner(job)
        except Exception as e:  # noqa: BLE001 — a crashed build must still end in a state the foreman can report
            store.add_event(job.id, "factory", f"Build crashed: {e}")
            store.update(job.id, state="failed", error=f"The factory hit an unexpected error: {e}")

    def activity_url(job_id: str) -> str:
        return f"{public_url()}/jobs/{job_id}"

    @mcp.tool()
    async def start_build(kind: str, spec: str) -> dict:
        """Start building something. kind is "dashboard" or "mantle_agent"; spec is the full description.
        Returns immediately with a job_id and a link where the build can be watched live."""
        if kind not in KINDS:
            return {"error": f"Unknown kind {kind!r}. Use one of: {', '.join(KINDS)}."}
        job = store.create(kind, spec)  # type: ignore[arg-type]
        store.add_event(job.id, "factory", f"Job received: build a {kind.replace('_', ' ')}.")
        t = asyncio.create_task(_run(job))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return {"job_id": job.id, "activity_url": activity_url(job.id)}

    @mcp.tool()
    async def build_status(job_id: str) -> dict:
        """How a build is going: state (queued, building, checking, fixing, passed, failed), round, recent activity."""
        job = store.get(job_id)
        if job is None:
            return {"state": "unknown",
                    "hint": "The factory doesn't know that job — it may have restarted. Start a new build."}
        recent = [f"{e.actor}: {e.text}" for e in job.events if not e.text.startswith("__")][-5:]
        return {"state": job.state, "round": job.round, "recent": recent, "activity_url": activity_url(job_id)}

    @mcp.tool()
    async def build_result(job_id: str) -> dict:
        """The outcome of a finished build: where to open it, a short summary, the checker's report, or the error."""
        job = store.get(job_id)
        if job is None:
            return {"state": "unknown",
                    "hint": "The factory doesn't know that job — it may have restarted. Start a new build."}
        return {"state": job.state, "result_url": job.result_url, "summary": job.summary,
                "check_report": job.check_report, "error": job.error}

    @mcp.custom_route("/jobs/{job_id}", methods=["GET"])
    async def activity_page(request: Request) -> HTMLResponse:
        return HTMLResponse(ACTIVITY_HTML.read_text() if ACTIVITY_HTML.exists() else "<p>activity</p>")

    @mcp.custom_route("/jobs/{job_id}/state", methods=["GET"])
    async def job_state(request: Request) -> JSONResponse:
        job = store.get(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"state": "unknown"}, status_code=404)
        return JSONResponse({"id": job.id, "kind": job.kind, "state": job.state, "round": job.round,
                             "result_url": job.result_url, "summary": job.summary, "error": job.error,
                             "check_report": job.check_report})

    @mcp.custom_route("/jobs/{job_id}/events", methods=["GET"])
    async def job_events(request: Request) -> StreamingResponse:
        job_id = request.path_params["job_id"]

        async def stream():
            if store.get(job_id) is None:
                return
            async for ev in store.subscribe(job_id):
                yield f"data: {json.dumps({'ts': ev.ts, 'actor': ev.actor, 'text': ev.text})}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return mcp


def main() -> None:
    import functools

    import uvicorn

    from factory.pipeline import run_job
    from factory.workspace import WORKSPACE

    export_settings()
    store = JobStore(WORKSPACE / "jobs")
    server = build_server(store, functools.partial(run_job, store=store))
    uvicorn.run(server.streamable_http_app(), host="0.0.0.0", port=int(os.environ.get("FACTORY_PORT", "8800")))


if __name__ == "__main__":
    main()
