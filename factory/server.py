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
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse

from factory.jobs import KINDS, Job, JobStore
from factory.specs import full_spec, revised_brief
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

    def launch(job: Job) -> dict:
        t = asyncio.create_task(_run(job))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return {"job_id": job.id, "activity_url": activity_url(job.id)}

    def find(job_id: str) -> Job | None:
        return store.get(job_id) if job_id else store.latest()

    unknown = {"state": "unknown",
               "hint": "The factory doesn't know that build - it may have restarted. Start a new build."}

    saved: dict[str, str] = {}  # the brief agreed with the person, waiting for their yes

    @mcp.tool()
    async def save_brief(kind: str, brief: str) -> dict:
        """Save the brief agreed with the person, replacing any earlier version. kind is "dashboard" or
        "mantle_agent". Nothing is built until start_build. Returns the saved brief so you can show it."""
        if kind not in KINDS:
            return {"error": f"Unknown kind {kind!r}. Use one of: {', '.join(KINDS)}."}
        saved.clear()
        saved[kind] = brief.strip()
        return {"kind": kind, "brief": saved[kind]}

    @mcp.tool()
    async def start_build() -> dict:
        """Build the brief most recently saved with save_brief (the factory adds its own fixed contract).
        Returns immediately with a job_id and a link where the build can be watched live."""
        if not saved:
            raise ToolError("No brief is saved. Agree a brief with the person and call save_brief first.")
        kind, brief = saved.popitem()
        job = store.create(kind, full_spec(kind, brief), brief=brief)  # type: ignore[arg-type]
        store.add_event(job.id, "factory", f"Job received: build a {kind.replace('_', ' ')}.")
        return launch(job)

    @mcp.tool()
    async def revise_build(change: str, kind: str = "", job_id: str = "") -> dict:
        """Change a finished build instead of starting over: the builder starts from what was built and the
        checker re-checks everything, including the change. change is one plain sentence describing what
        the person wants different. kind ("dashboard" or "mantle_agent") says which of their builds to
        change; without it, the most recent one."""
        latest = store.latest()
        if not job_id and latest is not None and latest.state not in ("passed", "failed"):
            raise ToolError("A build is still running, so this change can't start yet. Tell the person to "
                            "ask again once it has finished (the build page shows when). You can't message "
                            "them later, so don't promise to.")
        base = store.get(job_id) if job_id else store.latest(state="passed", kind=kind or None)
        if base is None or base.state != "passed":
            raise ToolError("There is nothing finished to change yet. Start a build first, or wait for one "
                            "to pass.")
        brief = revised_brief(base.brief, change)
        job = store.create(base.kind, full_spec(base.kind, brief), brief=brief, based_on=base.id,
                           change=change.strip())
        store.add_event(job.id, "factory", f"Job received: change the {base.kind.replace('_', ' ')}.")
        return launch(job)

    @mcp.tool()
    async def list_builds() -> dict:
        """The person's builds, newest first: job_id, kind, state, what each one was (the brief's first line
        or the change asked for), and result_url for the ones that passed."""
        builds = []
        for j in store.all()[:12]:
            what = j.change or (j.brief.strip().splitlines() or [""])[0]
            builds.append({"job_id": j.id, "kind": j.kind, "state": j.state, "what": what,
                           "result_url": j.result_url if j.state == "passed" else None})
        return {"builds": builds}

    @mcp.tool()
    async def get_brief(kind: str = "") -> dict:
        """The brief behind the latest build (of this kind, if given), including every change asked for since."""
        job = store.latest(kind=kind or None)
        if job is None:
            return {"error": "Nothing has been built yet."}
        return {"job_id": job.id, "kind": job.kind, "brief": job.brief}

    @mcp.tool()
    async def restore_build(job_id: str) -> dict:
        """Put an earlier build that passed back live (use list_builds to find it). Later changes build on it."""
        base = store.get(job_id)
        if base is None or base.state != "passed":
            raise ToolError("Only a build that passed can be restored. Use list_builds to pick one.")
        job = store.create(base.kind, base.spec, brief=base.brief, based_on=base.id,
                           change=f"Go back to build {base.id}.", restore=True)
        store.add_event(job.id, "factory", f"Job received: put build {base.id} back live.")
        return launch(job)

    @mcp.tool()
    async def build_status(job_id: str = "") -> dict:
        """How a build is going: state (queued, building, checking, fixing, passed, failed), round, recent
        activity. job_id defaults to the most recent build."""
        job = find(job_id)
        if job is None:
            return unknown
        recent = [f"{e.actor}: {e.text}" for e in job.events if not e.text.startswith("__")][-5:]
        return {"job_id": job.id, "state": job.state, "round": job.round, "recent": recent,
                "activity_url": activity_url(job.id)}

    @mcp.tool()
    async def build_result(job_id: str = "") -> dict:
        """The outcome of a finished build: where to open it, a short summary, the checker's report, or the
        error. job_id defaults to the most recent build."""
        job = find(job_id)
        if job is None:
            raise ToolError(unknown["hint"])
        if job.state not in ("passed", "failed"):
            raise ToolError(f"The build isn't finished yet (it is {job.state}). Use build_status to report progress.")
        return {"job_id": job.id, "state": job.state, "result_url": job.result_url, "summary": job.summary,
                "check_report": job.check_report, "error": job.error}

    @mcp.custom_route("/jobs/{job_id}", methods=["GET"])
    async def activity_page(request: Request) -> HTMLResponse:
        return HTMLResponse(ACTIVITY_HTML.read_text() if ACTIVITY_HTML.exists() else "<p>activity</p>")

    @mcp.custom_route("/jobs/latest/links", methods=["GET"])
    async def latest_links(request: Request) -> JSONResponse:
        """Labelled links for the latest build; the foreman turns them into buttons."""
        job = store.latest()
        links = []
        if job is not None:
            if job.state == "passed" and job.result_url:
                links.append({"title": "Open it", "url": job.result_url})
            links.append({"title": "Watch the build", "url": activity_url(job.id)})
        return JSONResponse({"links": links})

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
                yield sse_line(ev)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return mcp


def sse_line(ev) -> str:
    """One activity-page event: the line, what's behind it, and its position (a later detail updates that line)."""
    return f"data: {json.dumps({'ts': ev.ts, 'actor': ev.actor, 'text': ev.text, 'detail': ev.detail, 'seq': ev.seq})}\n\n"


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
