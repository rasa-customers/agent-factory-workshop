import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from factory.checks.dashboard import probe
from factory.checks.mantle import updates_since

REPO = Path(__file__).parents[2]
FIX = Path(__file__).parent / "fixtures"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _serve(tmp_path, fixture):
    root = tmp_path / fixture
    shutil.copytree(REPO / "templates" / "dashboard", root)
    shutil.copy(FIX / fixture / "index.html", root / "static" / "index.html")
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"dash_{fixture}", root / "app.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(mod.app, port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", root, server


@pytest.fixture
def dash_ok(tmp_path):
    url, root, server = _serve(tmp_path, "dash_ok")
    yield url, root
    server.should_exit = True


@pytest.fixture
def dash_flash(tmp_path):
    url, root, server = _serve(tmp_path, "dash_flash")
    yield url, root
    server.should_exit = True


@pytest.fixture
def dash_anim(tmp_path):
    url, root, server = _serve(tmp_path, "dash_anim")
    yield url, root
    server.should_exit = True


@pytest.fixture
def dash_err(tmp_path):
    url, root, server = _serve(tmp_path, "dash_err")
    yield url, root
    server.should_exit = True


async def test_probe_sees_text_change(dash_ok):
    url, root = dash_ok
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    assert "no flight yet" in r["text_before"]
    assert "B22" in r["text_after"]
    assert Path(r["screenshot_path"]).exists()


async def test_probe_reports_what_the_page_looks_like(dash_ok):
    url, root = dash_ok
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    look = r["look"]
    assert look["viewport"] == "tablet 1180x820"
    assert look["page_background"].startswith("rgb")
    assert look["largest_text"] and {"text", "font_px", "color"} <= set(look["largest_text"][0])
    assert look["largest_text"][0]["font_px"] >= look["largest_text"][-1]["font_px"]
    assert look["horizontal_overflow"] is False


async def test_probe_sees_a_background_painted_on_a_wrapper(dash_flash):
    url, root = dash_flash
    r = await probe(url, [], shots_dir=root)
    assert r["look"]["page_background"] == "rgb(10, 10, 20)"


async def test_probe_sees_a_brief_highlight_after_an_update(dash_flash):
    url, root = dash_flash
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    assert any("Gate B22" in h["text"] for h in r["look"]["highlighted_briefly"])


async def test_probe_reports_no_highlight_when_there_is_none(dash_ok):
    url, root = dash_ok
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    assert r["look"]["highlighted_briefly"] == []


async def test_probe_sees_a_short_animation_after_an_update(dash_anim):
    url, root = dash_anim
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    assert any("Gate B22" in a["text"] for a in r["look"]["animated"])


async def test_probe_reports_no_animation_when_there_is_none(dash_ok):
    url, root = dash_ok
    r = await probe(url, [{"panel": "flight", "data": {"gate": "B22"}}], shots_dir=root)
    assert r["look"]["animated"] == []


async def test_probe_reports_whether_there_is_a_map(dash_ok):
    url, root = dash_ok
    r = await probe(url, [], shots_dir=root)
    assert r["look"]["map"] == {"present": False, "tiles_loaded": 0, "markers": 0, "lines": 0}


async def test_probe_can_look_at_phone_width(dash_ok):
    url, root = dash_ok
    r = await probe(url, [], shots_dir=root, viewport="phone")
    assert r["look"]["viewport"] == "phone 390x844"


async def test_probes_at_the_same_time_do_not_mix_up_data(dash_ok):
    import asyncio
    url, root = dash_ok
    a, b = await asyncio.gather(probe(url, [{"panel": "flight", "data": {"gate": "A1"}}], shots_dir=root),
                                probe(url, [{"panel": "flight", "data": {"gate": "Z9"}}], shots_dir=root))
    assert "A1" in a["text_after"] and "Z9" in b["text_after"]


async def test_probe_captures_console_errors(dash_err):
    url, root = dash_err
    r = await probe(url, [], shots_dir=root)
    assert any("kaboom" in e for e in r["console_errors"])


def test_updates_since_filters():
    hist = [{"ts": 1.0, "panel": "flight"}, {"ts": 5.0, "panel": "weather"}]
    assert [h["panel"] for h in updates_since(hist, 2.0)] == ["weather"]


async def test_travel_truth_server_is_read_only():
    from factory.checks.mantle import TRUTH_TOOLS, travel_truth_server
    srv = travel_truth_server()
    assert srv.params["url"].endswith("/mcp/")
    assert set(TRUTH_TOOLS) == {"get_flight", "get_meeting", "get_weather", "estimate_travel_minutes",
                                "find_alternate_flights", "available_meeting_times"}
    assert "update_dashboard" not in TRUTH_TOOLS
