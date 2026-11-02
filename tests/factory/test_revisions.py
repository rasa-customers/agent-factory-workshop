"""Shaping a spec in conversation and changing a finished build: the factory side."""
import asyncio

from factory.jobs import Job
from factory.pipeline import builder_input
from factory.specs import CONTRACTS, full_spec
from factory.server import build_server
from factory.workspace import prepare_workspace
from tests.factory.conftest import build, call_tool


async def idle(job):
    return None


# --- the fixed contract travels with every brief -------------------------------------------------------

def test_full_spec_adds_the_dashboard_contract():
    spec = full_spec("dashboard", "A calm, light dashboard for my trip.")
    assert spec.startswith("A calm, light dashboard for my trip.")
    assert "api/events" in spec and "api/reset" in spec and "previous_gate" in spec


def test_full_spec_adds_the_agent_contract():
    spec = full_spec("mantle_agent", "A cheerful travel agent.")
    assert "update_dashboard" in spec and "Open your dashboard" in spec and "mcp/travel" in spec


def test_full_spec_does_not_repeat_a_contract_already_pasted():
    once = full_spec("dashboard", "brief")
    assert full_spec("dashboard", once) == once


def test_every_kind_has_a_contract():
    assert set(CONTRACTS) == {"dashboard", "mantle_agent"}


# --- start_build / revise_build ------------------------------------------------------------------------

async def test_start_build_checks_against_brief_plus_contract(store):
    server = build_server(store, idle)
    r = await build(server, "dashboard", "Light theme, verdict up top.")
    job = store.get(r["job_id"])
    assert job.brief == "Light theme, verdict up top."
    assert job.spec == full_spec("dashboard", "Light theme, verdict up top.")


async def passed_job(store, kind="dashboard", brief="Light theme."):
    job = store.create(kind, full_spec(kind, brief), brief=brief)
    store.update(job.id, state="passed", result_url="http://localhost:8600/")
    return job


async def test_revise_build_changes_the_latest_passed_build(store):
    base = await passed_job(store)
    server = build_server(store, idle)
    r = await call_tool(server, "revise_build", {"change": "Make the verdict twice as big."})
    job = store.get(r["job_id"])
    assert job.based_on == base.id and job.kind == "dashboard"
    assert job.change == "Make the verdict twice as big."
    assert "Light theme." in job.brief and "Make the verdict twice as big." in job.brief
    assert job.spec == full_spec("dashboard", job.brief)
    assert r["activity_url"].endswith(f"/jobs/{job.id}")


async def test_revise_build_chains_changes(store):
    await passed_job(store)
    server = build_server(store, idle)
    first = await call_tool(server, "revise_build", {"change": "Bigger verdict."})
    store.update(first["job_id"], state="passed")
    second = await call_tool(server, "revise_build", {"change": "Red when tight."})
    job = store.get(second["job_id"])
    assert job.based_on == first["job_id"]
    assert "Bigger verdict." in job.brief and "Red when tight." in job.brief


async def test_revise_build_can_target_a_job(store):
    dash = await passed_job(store)
    await passed_job(store, kind="mantle_agent", brief="Cheerful.")
    server = build_server(store, idle)
    r = await call_tool(server, "revise_build", {"change": "Bigger verdict.", "job_id": dash.id})
    assert store.get(r["job_id"]).kind == "dashboard"


async def test_revise_build_needs_a_finished_build(store):
    server = build_server(store, idle)
    r = await call_tool(server, "revise_build", {"change": "Bigger verdict."})
    assert "error" in r and "nothing" in r["error"].lower()


async def test_revise_build_waits_for_a_running_build(store):
    store.create("dashboard", "x", brief="x")  # still queued
    server = build_server(store, idle)
    r = await call_tool(server, "revise_build", {"change": "Bigger verdict."})
    assert "error" in r and "still" in r["error"].lower()


async def test_status_and_result_default_to_the_latest_job(store):
    server = build_server(store, idle)
    r = await build(server, "dashboard", "x")
    await asyncio.sleep(0.01)
    s = await call_tool(server, "build_status", {})
    assert s["job_id"] == r["job_id"]
    res = await call_tool(server, "build_result", {})
    assert res["job_id"] == r["job_id"]


async def test_status_with_no_jobs_says_so(store):
    server = build_server(store, idle)
    s = await call_tool(server, "build_status", {})
    assert s["state"] == "unknown"


# --- a revision starts from the previous build ---------------------------------------------------------

def test_revision_workspace_starts_from_the_previous_build(tmp_path):
    base = Job(id="b1", kind="dashboard", spec="s")
    root = prepare_workspace(base, base=tmp_path)
    (root / "static" / "index.html").write_text("<h1>the passed build</h1>")
    (root / "models").mkdir()
    (root / "models" / "big.tar.gz").write_text("x")
    rev = Job(id="r1", kind="dashboard", spec="s", based_on="b1", change="bigger")
    new = prepare_workspace(rev, base=tmp_path)
    assert (new / "static" / "index.html").read_text() == "<h1>the passed build</h1>"
    assert not (new / "models").exists()


def test_revision_without_previous_workspace_falls_back_to_template(tmp_path):
    rev = Job(id="r2", kind="dashboard", spec="s", based_on="gone", change="bigger")
    new = prepare_workspace(rev, base=tmp_path)
    assert (new / "app.py").exists()


def test_builder_is_told_to_change_not_rebuild():
    text = builder_input("SPEC TEXT", [], change="Make the verdict twice as big.")
    assert "already" in text and "Make the verdict twice as big." in text and "SPEC TEXT" in text


def test_builder_keeps_the_change_in_view_while_fixing():
    text = builder_input("SPEC TEXT", ["verdict too small"], change="Make the verdict twice as big.")
    assert "Make the verdict twice as big." in text and "verdict too small" in text
