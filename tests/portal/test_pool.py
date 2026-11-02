import pytest
from fastapi.testclient import TestClient

from infra.portal.app import create_app
from infra.portal.pool import Pool
from infra.portal.providers import FakeProvider


@pytest.fixture
def provider():
    return FakeProvider()


def make_pool(db, provider, warm=10, ceiling=60):
    return Pool(db, provider, warm=warm, ceiling=ceiling, domain="fw.example")


async def test_tick_fills_warm_pool(db, provider):
    pool = make_pool(db, provider)
    await pool.tick()
    assert len(db.vms("launching")) == 10 and len(provider.launched) == 10


async def test_tick_marks_ready(db, provider):
    pool = make_pool(db, provider, warm=2)
    await pool.tick()
    provider.ready_all()
    await pool.tick()
    assert len(db.vms("ready")) == 2


async def test_tick_respects_ceiling(db, provider):
    pool = make_pool(db, provider, warm=10, ceiling=3)
    await pool.tick(); await pool.tick()
    assert len(provider.launched) == 3


async def test_assign_is_idempotent(db, provider):
    pool = make_pool(db, provider, warm=2)
    await pool.tick(); provider.ready_all(); await pool.tick()
    db.add_attendee("a@x.io", "sk", "t1")
    v1 = await pool.assign("a@x.io")
    v2 = await pool.assign("a@x.io")
    assert v1["id"] == v2["id"] and db.attendee("a@x.io")["vm_id"] == v1["id"]


async def test_assign_prefers_ready_machine(db, provider):
    pool = make_pool(db, provider, warm=2)
    await pool.tick()
    provider.ready(db.vms()[1]["hostname"]); await pool.tick()
    db.add_attendee("a@x.io", "sk", "t1")
    v = await pool.assign("a@x.io")
    assert v["state"] == "ready"


async def test_assign_replenishes_on_next_tick(db, provider):
    pool = make_pool(db, provider, warm=2)
    await pool.tick()
    db.add_attendee("a@x.io", "sk", "t1")
    await pool.assign("a@x.io")
    await pool.tick()
    assert len(provider.launched) == 3


async def test_assign_launches_when_pool_empty(db, provider):
    pool = make_pool(db, provider, warm=0, ceiling=5)
    db.add_attendee("a@x.io", "sk", "t1")
    v = await pool.assign("a@x.io")
    assert v is not None and v["state"] == "launching"


async def test_full_when_at_ceiling(db, provider):
    pool = make_pool(db, provider, warm=1, ceiling=1)
    await pool.tick()
    db.add_attendee("a@x.io", "sk", "t1"); db.add_attendee("b@x.io", "sk2", "t2")
    await pool.assign("a@x.io")
    assert await pool.assign("b@x.io") is None
    assert (await pool.status_for("b@x.io"))["state"] == "full"


async def test_scale_adds_machines_up_to_ceiling(db, provider):
    pool = make_pool(db, provider, warm=0, ceiling=4)
    await pool.scale(10)
    assert len(provider.launched) == 4


@pytest.fixture
def cloud_client(db, minter, provider, monkeypatch):
    monkeypatch.setenv("PROXY_BASE_URL", "https://llm.example/v1")
    pool = make_pool(db, provider, warm=0, ceiling=5)
    return TestClient(create_app(db=db, minter=minter, pool=pool)), pool


def test_choose_cloud_with_empty_pool_queues_attendee(cloud_client, provider):
    client, pool = cloud_client
    client.post("/signup", data={"email": "ipad@x.io"})
    client.post("/choose", data={"choice": "cloud"})
    assert client.get("/me/vm").json()["state"] == "starting"
    provider.ready_all()
    import asyncio; asyncio.run(pool.tick())
    s = client.get("/me/vm").json()
    assert s["state"] == "ready" and s["url"].startswith("https://vm-") and s["password"]


def test_internal_config_requires_secret(cloud_client, db):
    client, _ = cloud_client
    client.post("/signup", data={"email": "ipad@x.io"})
    client.post("/choose", data={"choice": "cloud"})
    vm = db.vms()[0]
    assert client.get(f"/internal/vm/{vm['id']}/config").status_code == 403
    assert client.get(f"/internal/vm/{vm['id']}/config", headers={"X-Config-Secret": "wrong"}).status_code == 403


def test_config_includes_license_after_paste(cloud_client, db):
    client, _ = cloud_client
    client.post("/signup", data={"email": "ipad@x.io"})
    client.post("/choose", data={"choice": "cloud"})
    client.post("/license", data={"license": "LIC-9"})
    vm = db.vms()[0]
    cfg = client.get(f"/internal/vm/{vm['id']}/config", headers={"X-Config-Secret": vm["config_secret"]}).json()
    assert cfg["assigned"] and cfg["env"]["RASA_LICENSE"] == "LIC-9" and cfg["env"]["OPENAI_API_KEY"].startswith("sk-fake")


def test_config_sends_the_studio_address_when_studio_is_set_up(cloud_client, db, monkeypatch):
    monkeypatch.setenv("STUDIO_KAFKA_URL", "10.77.1.9:29092")
    client, _ = cloud_client
    client.post("/signup", data={"email": "studio@x.io"})
    client.post("/choose", data={"choice": "cloud"})
    vm = db.vms()[0]
    cfg = client.get(f"/internal/vm/{vm['id']}/config", headers={"X-Config-Secret": vm["config_secret"]}).json()
    assert cfg["env"]["STUDIO_KAFKA_URL"] == "10.77.1.9:29092"


async def test_ready_machine_records_ip_and_notifies(db, provider):
    seen = []

    async def on_change(vms):
        seen.append([v["ip"] for v in vms])
    pool = Pool(db, provider, warm=1, ceiling=2, domain="fw.example", on_change=on_change)
    await pool.tick(); provider.ready_all(); await pool.tick()
    assert db.vms("ready")[0]["ip"] == "10.0.0.10" and seen == [["10.0.0.10"]]


class FlakyProvider(FakeProvider):
    """Fails its first launch (e.g. the launch template doesn't exist yet)."""

    def __init__(self):
        super().__init__()
        self.fail_next = True

    async def launch(self, vm_id, hostname, config_secret):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("InvalidLaunchTemplateName.NotFound")
        return await super().launch(vm_id, hostname, config_secret)


async def test_failed_launch_is_marked_failed_and_pool_recovers(db):
    provider = FlakyProvider()
    pool = make_pool(db, provider, warm=2)
    await pool.tick()          # first launch fails: no crash, nothing half-made counted as active
    assert [v["state"] for v in db.vms("failed")] == ["failed"]
    n = len(db.vms())          # launches run side by side: one failed, the other is launching
    await pool.tick()          # backs off for a minute: no new rows at all
    assert len(db.vms()) == n
    pool._retry_after = 0
    await pool.tick()          # later ticks keep working and fill the pool
    provider.ready_all()
    await pool.tick()
    assert len(db.vms("ready")) == 2


async def test_ready_status_opens_repo_and_reports_whether_the_foreman_is_up(db, provider):
    pool = make_pool(db, provider, warm=1)
    await pool.tick(); provider.ready_all(); await pool.tick()
    db.add_attendee("a@x.io", "sk", "t1"); db.set_attendee("a@x.io", choice="cloud")
    s = await pool.status_for("a@x.io")
    assert s["state"] == "ready"
    assert s["url"].endswith("/?folder=/home/workshop/agent-factory-workshop")
    assert s["license"] is False and s["foreman_up"] is False
    db.set_attendee("a@x.io", license="LIC"); provider.services_up_all()
    s = await pool.status_for("a@x.io")
    assert s["license"] is True and s["foreman_up"] is True


async def test_machine_ids_are_not_guessable(db, provider):
    import re
    pool = make_pool(db, provider, warm=3)
    await pool.tick()
    ids = [v["id"] for v in db.vms()]
    assert all(re.fullmatch(r"vm-[0-9a-f]{8}", i) for i in ids) and len(set(ids)) == 3


async def test_assign_is_not_held_up_by_slow_readiness_checks(db):
    import asyncio, time

    class SlowProvider(FakeProvider):
        async def is_ready(self, vm):
            await asyncio.sleep(0.5)  # an EC2 call + health check timing out on a booting machine
            return None

    provider = SlowProvider()
    pool = make_pool(db, provider, warm=4)
    await pool.tick()                       # 4 machines launching
    db.add_attendee("a@x.io", "sk", "t1")
    ticking = asyncio.create_task(pool.tick())
    await asyncio.sleep(0.05)
    t0 = time.perf_counter()
    vm = await pool.assign("a@x.io")
    assert vm is not None and time.perf_counter() - t0 < 0.2
    started = time.perf_counter(); await ticking
    assert time.perf_counter() - started < 0.6  # the four checks ran side by side, not one after another


async def test_a_failed_router_update_is_retried_next_tick(db, provider):
    pushes = []

    async def flaky_push(vms):
        pushes.append(len(vms))
        if len(pushes) == 1:
            raise RuntimeError("caddy restarting")

    pool = Pool(db, provider, warm=1, ceiling=5, domain="fw.example", on_change=flaky_push)
    await pool.tick(); provider.ready_all()
    await pool.tick()   # becomes ready, push fails (must not raise or skip refilling)
    await pool.tick()   # nothing new became ready, but the failed push is retried
    assert pushes == [1, 1]
