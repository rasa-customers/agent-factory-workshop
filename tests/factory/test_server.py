import asyncio
import time

import pytest

from factory.server import build_server
from tests.factory.conftest import build, call_tool


@pytest.fixture
def slow_server(store):
    async def runner(job):
        await asyncio.sleep(5)
    return build_server(store, runner)


async def test_start_build_returns_immediately(slow_server):
    t0 = time.monotonic()
    r = await build(slow_server, "dashboard", "a dashboard")
    assert time.monotonic() - t0 < 0.5
    assert r["job_id"] and r["activity_url"].endswith(f"/jobs/{r['job_id']}")


async def test_status_reports_recent_events(store):
    async def runner(job):
        for i in range(7):
            store.add_event(job.id, "builder", f"step {i}")
    server = build_server(store, runner)
    r = await build(server, "dashboard", "x")
    await asyncio.sleep(0.05)
    s = await call_tool(server, "build_status", {"job_id": r["job_id"]})
    assert s["recent"] == [f"builder: step {i}" for i in range(2, 7)]


async def test_status_unknown_job(slow_server):
    s = await call_tool(slow_server, "build_status", {"job_id": "missing"})
    assert s["state"] == "unknown" and "restart" in s["hint"]


async def test_result_unknown_job(slow_server):
    s = await call_tool(slow_server, "build_result", {"job_id": "missing"})
    assert s.get("is_error") and "restart" in s["error"]


async def test_save_brief_rejects_unknown_kind(slow_server):
    r = await call_tool(slow_server, "save_brief", {"kind": "spaceship", "brief": "x"})
    assert "error" in r and "dashboard" in r["error"]


async def test_start_build_builds_the_latest_saved_brief(store, slow_server):
    await call_tool(slow_server, "save_brief", {"kind": "dashboard", "brief": "Dark theme."})
    saved = await call_tool(slow_server, "save_brief", {"kind": "dashboard", "brief": "Dark theme. Big address."})
    assert saved["brief"] == "Dark theme. Big address."
    r = await call_tool(slow_server, "start_build", {})
    assert store.get(r["job_id"]).brief == "Dark theme. Big address."


async def test_start_build_needs_a_saved_brief(slow_server):
    r = await call_tool(slow_server, "start_build", {})
    assert r.get("is_error") and "save_brief" in r["error"]


async def test_a_saved_brief_is_built_once(slow_server):
    await build(slow_server, "dashboard", "x")
    r = await call_tool(slow_server, "start_build", {})
    assert "error" in r


async def test_runner_crash_marks_job_failed(store):
    async def runner(job):
        raise RuntimeError("boom")
    server = build_server(store, runner)
    r = await build(server, "dashboard", "x")
    await asyncio.sleep(0.05)
    assert store.get(r["job_id"]).state == "failed"


def test_latest_links_give_the_activity_page_then_the_result(store):
    from starlette.testclient import TestClient

    server = build_server(store, lambda job: None)
    http = TestClient(server.streamable_http_app())
    assert http.get("/jobs/latest/links").json() == {"links": []}
    job = store.create("dashboard", "x")
    links = http.get("/jobs/latest/links").json()["links"]
    assert links == [{"title": "Watch the build", "url": f"http://localhost:8800/jobs/{job.id}"}]
    store.update(job.id, state="passed", result_url="http://localhost:8600/")
    links = http.get("/jobs/latest/links").json()["links"]
    assert links[0] == {"title": "Open it", "url": "http://localhost:8600/"}
    assert links[1]["title"] == "Watch the build"
