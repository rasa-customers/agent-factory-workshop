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


def test_jobs_cut_off_by_a_restart_are_marked_failed_on_reload(store, tmp_path):
    job = store.create("dashboard", "spec")
    store.update(job.id, state="building", round=1)
    done = store.create("dashboard", "spec2")
    store.update(done.id, state="passed")
    reloaded = JobStore(tmp_path / "jobs")
    j = reloaded.get(job.id)
    assert j.state == "failed" and "restarted" in j.error and "start" in j.error
    assert reloaded.get(done.id).state == "passed"


def test_an_event_can_carry_detail_to_expand(store, tmp_path):
    job = store.create("dashboard", "spec")
    store.add_event(job.id, "builder", "→ write_file", detail='{"path": "index.html"}')
    again = JobStore(tmp_path / "jobs")
    ev = again.get(job.id).events[-1]
    assert ev.text == "→ write_file" and ev.detail == '{"path": "index.html"}'


def test_jobs_saved_before_details_existed_still_load(store, tmp_path):
    job = store.create("dashboard", "spec")
    path = tmp_path / "jobs" / f"{job.id}.json"
    data = json.loads(path.read_text())
    data["events"] = [{"ts": 1.0, "actor": "builder", "text": "Round 1: building."}]
    path.write_text(json.dumps(data))
    ev = JobStore(tmp_path / "jobs").get(job.id).events[0]
    assert ev.text == "Round 1: building." and ev.detail == ""


async def test_adding_detail_later_resends_the_same_line(store):
    job = store.create("dashboard", "spec")
    seq = store.add_event(job.id, "builder", "→ train_project", detail="args")
    it = store.subscribe(job.id)
    assert (await it.__anext__()).seq == seq
    store.add_detail(job.id, seq, "result: trained")
    ev = await it.__anext__()
    assert ev.seq == seq and ev.text == "→ train_project" and ev.detail == "args\n\nresult: trained"
    assert len(store.get(job.id).events) == 1
