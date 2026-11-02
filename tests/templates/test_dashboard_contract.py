import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

APP = Path(__file__).parents[2] / "templates" / "dashboard" / "app.py"


@pytest.fixture
def client():
    spec = importlib.util.spec_from_file_location("dash_app", APP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return TestClient(mod.app), mod


def test_post_then_get_state(client):
    c, _ = client
    c.post("/api/state", json={"panel": "flight", "data": {"gate": "B22"}})
    s = c.get("/api/state").json()
    assert s["flight"] == {"gate": "B22"} and s["weather"] is None


def test_post_merges_into_panel(client):
    c, _ = client
    c.post("/api/state", json={"panel": "flight", "data": {"gate": "B22"}})
    c.post("/api/state", json={"panel": "flight", "data": {"status": "Delayed"}})
    assert c.get("/api/state").json()["flight"] == {"gate": "B22", "status": "Delayed"}


def test_unknown_panel_rejected_422(client):
    c, _ = client
    assert c.post("/api/state", json={"panel": "nope", "data": {}}).status_code == 422


def test_reset_clears_state(client):
    c, _ = client
    c.post("/api/state", json={"panel": "verdict", "data": {"ok": True}})
    c.post("/api/reset")
    assert c.get("/api/state").json()["verdict"] is None


async def test_events_stream_emits_after_post(client):
    _, mod = client
    sub = mod.hub.subscribe()
    first = await sub.__anext__()
    assert json.loads(first)["flight"] is None
    await mod.set_panel("flight", {"gate": "B22"})
    second = await sub.__anext__()
    assert json.loads(second)["flight"] == {"gate": "B22"}


def test_index_served(client):
    c, _ = client
    assert "factory" in c.get("/").text.lower()
