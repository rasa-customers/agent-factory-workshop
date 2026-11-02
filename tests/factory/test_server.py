import asyncio
import time

import pytest

from factory.server import build_server
from tests.factory.conftest import call_tool


@pytest.fixture
def slow_server(store):
    async def runner(job):
        await asyncio.sleep(5)
    return build_server(store, runner)


async def test_start_build_returns_immediately(slow_server):
    t0 = time.monotonic()
    r = await call_tool(slow_server, "start_build", {"kind": "dashboard", "spec": "a dashboard"})
    assert time.monotonic() - t0 < 0.5
    assert r["job_id"] and r["activity_url"].endswith(f"/jobs/{r['job_id']}")


async def test_status_reports_recent_events(store):
    async def runner(job):
        for i in range(7):
            store.add_event(job.id, "builder", f"step {i}")
    server = build_server(store, runner)
    r = await call_tool(server, "start_build", {"kind": "dashboard", "spec": "x"})
    await asyncio.sleep(0.05)
    s = await call_tool(server, "build_status", {"job_id": r["job_id"]})
    assert s["recent"] == [f"builder: step {i}" for i in range(2, 7)]


async def test_status_unknown_job(slow_server):
    s = await call_tool(slow_server, "build_status", {"job_id": "missing"})
    assert s["state"] == "unknown" and "restart" in s["hint"]


async def test_result_unknown_job(slow_server):
    s = await call_tool(slow_server, "build_result", {"job_id": "missing"})
    assert s["state"] == "unknown"


async def test_start_build_rejects_unknown_kind(slow_server):
    r = await call_tool(slow_server, "start_build", {"kind": "spaceship", "spec": "x"})
    assert "error" in r and "dashboard" in r["error"]


async def test_runner_crash_marks_job_failed(store):
    async def runner(job):
        raise RuntimeError("boom")
    server = build_server(store, runner)
    r = await call_tool(server, "start_build", {"kind": "dashboard", "spec": "x"})
    await asyncio.sleep(0.05)
    assert store.get(r["job_id"]).state == "failed"
