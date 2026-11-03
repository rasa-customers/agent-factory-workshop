"""The richer trip: alternate flights, a meeting that can move, coordinates for a map, and a reset."""
from datetime import datetime, timedelta

import httpx
from starlette.testclient import TestClient

from travel_mcp import server


def minutes_between(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60


async def test_alternate_flights_land_at_different_airports(call):
    alts = await call("find_alternate_flights", {})
    assert len(alts["flights"]) == 3
    assert {f["arrival_airport"] for f in alts["flights"]} >= {"LGA", "EWR"}
    for f in alts["flights"]:
        assert {"flight_number", "airline", "departs", "estimated_arrival", "seats_left"} <= set(f)


async def test_an_alternate_can_turn_tight_into_yes(call):
    meeting = await call("get_meeting", {})
    best = None
    for f in (await call("find_alternate_flights", {}))["flights"]:
        leave = (datetime.fromisoformat(f["estimated_arrival"]) + timedelta(minutes=15)).isoformat()
        trip = await call("estimate_travel_minutes", {"origin": f["arrival_airport"], "destination_address": meeting["address"],
                                                      "depart_at": leave})
        slack = minutes_between(trip["arrives_at"], meeting["start"])
        best = slack if best is None else max(best, slack)
    assert best >= 15


async def test_laguardia_is_closer_than_jfk(call):
    args = {"destination_address": "1 Vanderbilt Ave", "depart_at": "2026-11-03T13:30:00-05:00"}
    jfk = await call("estimate_travel_minutes", {"origin": "JFK", **args})
    lga = await call("estimate_travel_minutes", {"origin": "LGA", **args})
    assert lga["minutes"] < jfk["minutes"]


async def test_meeting_can_move_to_an_offered_slot(call):
    before = await call("get_meeting", {})
    slots = (await call("available_meeting_times", {}))["slots"]
    assert slots and all(minutes_between(before["start"], s) > 0 for s in slots)
    moved = await call("reschedule_meeting", {"start": slots[0]})
    assert moved["ok"] is True and moved["meeting"]["start"] == slots[0]
    assert (await call("get_meeting", {}))["start"] == slots[0]


async def test_meeting_refuses_a_time_that_was_not_offered(call):
    r = await call("reschedule_meeting", {"start": "2026-11-03T03:00:00-05:00"})
    assert r["ok"] is False and "available_meeting_times" in r["error"]


async def test_one_slot_gives_at_least_15_minutes_by_car(call):
    flight = await call("get_flight", {})
    meeting = await call("get_meeting", {})
    leave = (datetime.fromisoformat(flight["estimated_arrival"]) + timedelta(minutes=15)).isoformat()
    trip = await call("estimate_travel_minutes", {"origin": "JFK", "destination_address": meeting["address"], "depart_at": leave})
    slots = (await call("available_meeting_times", {}))["slots"]
    assert any(minutes_between(trip["arrives_at"], s) >= 15 for s in slots)


async def test_travel_estimate_carries_coordinates_for_a_map(call):
    r = await call("estimate_travel_minutes", {"origin": "LGA", "destination_address": "1 Vanderbilt Ave",
                                               "depart_at": "2026-11-03T13:30:00-05:00"})
    assert r["from"]["name"] == "LaGuardia" and {"lat", "lon"} <= set(r["from"]) and {"lat", "lon"} <= set(r["to"])


async def test_flight_and_meeting_stay_flat_for_the_dashboard(call):
    for data in (await call("get_flight", {}), await call("get_meeting", {}),
                 *(await call("find_alternate_flights", {}))["flights"]):
        assert not any(isinstance(v, (dict, list)) for v in data.values())


async def test_route_is_a_dashboard_panel(call, respx_mock):
    respx_mock.post("http://localhost:8600/api/state").mock(return_value=httpx.Response(200, json={}))
    r = await call("update_dashboard", {"panel": "route", "data": {"from": "JFK", "to": "1 Vanderbilt Ave"}})
    assert r["ok"] is True


async def test_reset_puts_the_meeting_back(call):
    original = (await call("get_meeting", {}))["start"]
    slot = (await call("available_meeting_times", {}))["slots"][0]
    await call("reschedule_meeting", {"start": slot})
    http = TestClient(server.mcp.streamable_http_app())
    assert http.post("/reset").status_code == 200
    assert (await call("get_meeting", {}))["start"] == original


def test_reset_is_not_a_tool_built_agents_could_call():
    import asyncio
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "reset" not in names and "reset_trip" not in names


async def test_each_alternate_says_how_much_time_it_leaves_by_car(call):
    """So the agent never does the arithmetic itself: land + 15 minutes to deplane + the taxi, against the meeting."""
    by_number = {f["flight_number"]: f for f in (await call("find_alternate_flights", {}))["flights"]}
    assert by_number["RA 2030"]["slack_minutes_by_car"] == 45
    assert by_number["SK 418"]["slack_minutes_by_car"] == -20
    assert by_number["RA 2048"]["slack_minutes_by_car"] == -45


async def test_alternate_slack_follows_a_moved_meeting(call):
    slot = (await call("available_meeting_times", {}))["slots"][0]  # 14:45
    await call("reschedule_meeting", {"start": slot})
    by_number = {f["flight_number"]: f for f in (await call("find_alternate_flights", {}))["flights"]}
    assert by_number["SK 418"]["slack_minutes_by_car"] == -5
