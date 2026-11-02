import json

from factory.jobs import JobStore


def test_create_and_get_job(store):
    job = store.create("dashboard", "build a dashboard")
    got = store.get(job.id)
    assert got.kind == "dashboard" and got.state == "queued" and got.round == 0


def test_events_persist_to_disk(store, tmp_path):
    job = store.create("dashboard", "spec")
    store.add_event(job.id, "builder", "wrote index.html")
    data = json.loads((tmp_path / "jobs" / f"{job.id}.json").read_text())
    assert data["events"][-1]["text"] == "wrote index.html"


def test_jobs_reload_from_disk(store, tmp_path):
    job = store.create("dashboard", "spec")
    store.update(job.id, state="passed", result_url="http://x")
    again = JobStore(tmp_path / "jobs")
    assert again.get(job.id).state == "passed"


def test_get_unknown_returns_none(store):
    assert store.get("nope") is None


async def test_subscribe_replays_then_streams(store):
    job = store.create("dashboard", "spec")
    store.add_event(job.id, "factory", "first")
    it = store.subscribe(job.id)
    assert (await it.__anext__()).text == "first"
    store.add_event(job.id, "checker", "second")
    assert (await it.__anext__()).text == "second"
