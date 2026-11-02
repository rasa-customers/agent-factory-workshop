import httpx

DASH = "http://localhost:8600"


async def test_get_flight_defaults_to_the_nyc_flight(call):
    f = await call("get_flight", {})
    assert f["destination"] == "JFK"
    assert f["delay_minutes"] == 40
    assert f["gate"] != f["previous_gate"]
    assert f["status"] == "Delayed"


async def test_get_meeting_is_in_new_york(call):
    m = await call("get_meeting", {})
    assert "New York" in m["address"] and m["start"]


async def test_estimate_travel_minutes(call):
    r = await call("estimate_travel_minutes", {"origin": "JFK", "destination_address": "1 Vanderbilt Ave", "depart_at": "2026-11-03T13:30:00-05:00"})
    assert r["minutes"] == 55 and r["mode"] == "car"


async def test_estimate_travel_returns_arrival_clock_time(call):
    r = await call("estimate_travel_minutes", {"origin": "JFK", "destination_address": "1 Vanderbilt Ave", "depart_at": "2026-11-03T13:30:00-05:00"})
    assert r["arrives_at"] == "2026-11-03T14:25:00-05:00"


async def test_subway_is_slower_but_predictable(call):
    r = await call("estimate_travel_minutes", {"origin": "JFK", "destination_address": "1 Vanderbilt Ave", "depart_at": "2026-11-03T13:30:00-05:00", "mode": "subway"})
    assert r["mode"] == "subway" and r["minutes"] > 55


async def test_update_dashboard_posts_and_records(call, respx_mock):
    route = respx_mock.post(f"{DASH}/api/state").mock(return_value=httpx.Response(200, json={}))
    r = await call("update_dashboard", {"panel": "flight", "data": {"x": 1}})
    assert r["ok"] is True and route.called
    hist = await call("get_dashboard_history", {})
    assert hist[-1]["panel"] == "flight" and hist[-1]["ok"] is True and "ts" in hist[-1]


async def test_update_dashboard_reports_unreachable_dashboard(call, respx_mock):
    respx_mock.post(f"{DASH}/api/state").mock(side_effect=httpx.ConnectError("refused"))
    r = await call("update_dashboard", {"panel": "flight", "data": {}})
    assert r["ok"] is False and "dashboard" in r["error"].lower()
