import httpx
import respx

from factory.example_data import example_panels, seed_dashboard


async def test_example_panels_fill_all_four_with_the_workshop_trip(monkeypatch):
    async def fake_weather(location, at):
        return {"temperature_c": 9.0, "condition": "Overcast", "source": "open-meteo"}
    monkeypatch.setattr("factory.example_data.get_weather", fake_weather)
    p = await example_panels()
    assert set(p) == {"flight", "weather", "meeting", "verdict"}
    assert p["flight"]["flight_number"] == "RA 2026" and p["meeting"]["title"] == "Partner review"
    # ETA 13:15 + 15 min to get off + 55 min by car = 14:25 for a 14:30 meeting
    assert p["verdict"]["status"] == "tight" and p["verdict"]["slack_minutes"] == 5
    assert all("example" in str(d.get("note", "")).lower() for d in p.values())


@respx.mock
async def test_seed_dashboard_posts_every_panel(monkeypatch):
    async def fake_weather(location, at):
        return {"temperature_c": 9.0, "condition": "Overcast"}
    monkeypatch.setattr("factory.example_data.get_weather", fake_weather)
    route = respx.post("http://localhost:8600/api/state").mock(return_value=httpx.Response(200, json={}))
    assert await seed_dashboard("http://localhost:8600") is True
    assert route.call_count == 4


async def test_seed_dashboard_never_raises(monkeypatch):
    async def boom(location, at):
        raise RuntimeError("offline")
    monkeypatch.setattr("factory.example_data.get_weather", boom)
    assert await seed_dashboard("http://127.0.0.1:9") is False
