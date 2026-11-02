from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import openai
import pytest

from factory.agents import CheckItem, CheckReport
from factory.pipeline import run_job


class FakeHost:
    def __init__(self):
        self.started = []

    async def start(self, kind, root):
        self.started.append((kind, root))
        return "http://localhost:8600/"

    async def promote(self, kind, root):
        self.promoted = (kind, root)


class FakeWorkers:
    """Stands in for the real builder/checker agents; run_agent tells them apart by name."""

    @asynccontextmanager
    async def session(self, job, root):
        yield SimpleNamespace(builder=SimpleNamespace(name="Builder"),
                              checker_for=lambda url: SimpleNamespace(name="Checker"))


def report(ok, text="panel shows gate"):
    return CheckReport(passed=ok, items=[CheckItem(expectation=text, passed=ok, evidence="seen" if ok else "missing")])


def scripted(*reports):
    calls = {"builder_inputs": [], "checks": list(reports)}

    async def run_agent(agent, input, **kw):
        if agent.name == "Builder":
            calls["builder_inputs"].append(input)
            return SimpleNamespace(final_output="Built a dashboard with four panels.")
        return SimpleNamespace(final_output=calls["checks"].pop(0))
    return run_agent, calls


@pytest.fixture
def job(store):
    return store.create("dashboard", "A flight dashboard with a gate panel.")


async def go(job, store, run_agent, tmp_path, host=None, max_rounds=3):
    host = host or FakeHost()
    await run_job(job, store, run_agent=run_agent, host=host, workers=FakeWorkers(),
                  max_rounds=max_rounds, workspace_base=tmp_path / "ws")
    return store.get(job.id), host


async def test_pipeline_passes_first_round(job, store, tmp_path):
    run_agent, calls = scripted(report(True))
    j, host = await go(job, store, run_agent, tmp_path)
    assert j.state == "passed" and j.round == 1 and j.result_url == "http://localhost:8600/"
    assert j.summary == "Built a dashboard with four panels."
    assert host.promoted[0] == "dashboard"


async def test_pipeline_feeds_failures_back(job, store, tmp_path):
    run_agent, calls = scripted(report(False, "verdict panel shows minutes of slack"), report(True))
    j, _ = await go(job, store, run_agent, tmp_path)
    assert j.state == "passed" and j.round == 2
    assert "verdict panel shows minutes of slack" in calls["builder_inputs"][1]


async def test_pipeline_fails_after_max_rounds(job, store, tmp_path):
    run_agent, _ = scripted(report(False), report(False), report(False))
    j, _ = await go(job, store, run_agent, tmp_path)
    assert j.state == "failed" and "uv run workshop checkpoint 02-dashboard-built" in j.error


async def test_pipeline_marks_failed_on_llm_error(job, store, tmp_path):
    async def run_agent(agent, input, **kw):
        resp = httpx.Response(400, request=httpx.Request("POST", "http://p/v1/chat"))
        raise openai.BadRequestError("Budget has been exceeded! Current cost: 5.1", response=resp, body=None)
    j, _ = await go(job, store, run_agent, tmp_path)
    assert j.state == "failed" and "budget" in j.error.lower()
    assert "uv run workshop checkpoint 02-dashboard-built" in j.error  # every failure offers the way forward


async def test_pipeline_rate_limit_message(job, store, tmp_path):
    async def run_agent(agent, input, **kw):
        resp = httpx.Response(429, request=httpx.Request("POST", "http://p/v1/chat"))
        raise openai.RateLimitError("Rate limit reached", response=resp, body=None)
    j, _ = await go(job, store, run_agent, tmp_path)
    assert j.state == "failed" and "busy" in j.error.lower()


async def test_events_recorded_for_builder_and_checker(job, store, tmp_path):
    run_agent, _ = scripted(report(True))
    j, _ = await go(job, store, run_agent, tmp_path)
    actors = {e.actor for e in j.events}
    assert {"factory", "builder", "checker"} <= actors
    assert any("✓" in e.text for e in j.events if e.actor == "checker")


class FailsOnceHost(FakeHost):
    async def start(self, kind, root):
        from factory.hosting import StartFailed
        if not self.started:
            self.started.append((kind, root))
            raise StartFailed("It didn't train: Skill 'skills/x' failed to load: Unknown key(s): id")
        return await super().start(kind, root)


async def test_start_failure_goes_back_to_builder_not_crash(job, store, tmp_path):
    run_agent, calls = scripted(report(True))
    j, _ = await go(job, store, run_agent, tmp_path, host=FailsOnceHost())
    assert j.state == "passed" and j.round == 2
    assert "Unknown key(s): id" in calls["builder_inputs"][1]


def test_train_errors_are_summarised():
    from factory.hosting import train_errors
    out = ('noise\n{"event_info": "Project validation found 1 problem(s):\\n  - [x] Skill bad: Unknown key(s): id", '
           '"level": "error"}\nmore noise')
    assert "Unknown key(s): id" in train_errors(out)


async def test_a_passed_dashboard_gets_the_example_trip(job, store, tmp_path):
    seeded = []

    async def seed(url):
        seeded.append(url)
        return True

    run_agent, _ = scripted(report(True))
    await run_job(job, store, run_agent=run_agent, host=FakeHost(), workers=FakeWorkers(),
                  workspace_base=tmp_path / "ws", seed=seed)
    assert seeded == ["http://localhost:8600"]
    assert any("example" in e.text.lower() for e in store.get(job.id).events)


async def test_a_revision_builds_on_the_previous_workspace(store, tmp_path):
    base = store.create("dashboard", "A dashboard.")
    run_agent, _ = scripted(report(True))
    await go(base, store, run_agent, tmp_path)
    (tmp_path / "ws" / base.id / "static" / "index.html").write_text("<h1>first build</h1>")
    rev = store.create("dashboard", "A dashboard. Bigger verdict.", based_on=base.id, change="Bigger verdict.")
    run_agent, calls = scripted(report(True))
    j, _ = await go(rev, store, run_agent, tmp_path)
    assert j.state == "passed"
    assert "Bigger verdict." in calls["builder_inputs"][0] and "already" in calls["builder_inputs"][0]
    assert (tmp_path / "ws" / rev.id / "static" / "index.html").read_text() == "<h1>first build</h1>"
    assert any("changing: Bigger verdict." in e.text for e in j.events)
