"""Travel tools for the workshop, served over MCP on :8700.

Mock flight, alternates and meeting, real weather, and a bridge that pushes facts onto the dashboard.
POST /reset (plain HTTP, not a tool) puts the trip back the way it started; the factory calls it before
every check so one conversation's reschedule can't leak into the next.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from travel_mcp import flight_data, weather

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8600")
DASHBOARD_HISTORY: list[dict[str, Any]] = []

mcp = FastMCP("travel", host="0.0.0.0", port=int(os.environ.get("TRAVEL_MCP_PORT", "8700")))


@mcp.tool()
async def get_flight(flight_number: str | None = None, destination: str | None = None) -> dict:
    """The traveller's booked flight (no arguments needed): status, delay, gate (and previous gate), and arrival times."""
    return flight_data.flight()


@mcp.tool()
async def get_weather(location: str, at: str) -> dict:
    """Weather forecast for a place at a time (ISO-8601 with offset), e.g. when the flight lands."""
    return await weather.get_weather(location, at)


@mcp.tool()
async def get_meeting() -> dict:
    """The traveller's next meeting: title, start time, and address."""
    return flight_data.meeting()


@mcp.tool()
async def estimate_travel_minutes(origin: str, destination_address: str, depart_at: str,
                                  mode: Literal["car", "subway"] = "car") -> dict:
    """Estimate door-to-door travel time from an airport (JFK, LGA or EWR) to an address, by car or subway.
    Returns the minutes and `arrives_at`: the clock time you'd arrive if you leave at depart_at."""
    code = flight_data.airport(origin)
    minutes, note = flight_data.TRAVEL[(code, mode)]
    try:
        arrives_at = (datetime.fromisoformat(depart_at) + timedelta(minutes=minutes)).isoformat()
    except ValueError:
        arrives_at = None
    return {"minutes": minutes, "mode": mode, "origin": code, "arrives_at": arrives_at, "note": note,
            "from": flight_data.AIRPORTS[code], "to": flight_data.MEETING_LOCATION}


@mcp.tool()
async def find_alternate_flights() -> dict:
    """Other flights from Chicago to New York today that still have seats, with where and when they land.
    Use estimate_travel_minutes from each one's arrival_airport to compare them."""
    return {"flights": flight_data.alternate_flights()}


@mcp.tool()
async def available_meeting_times() -> dict:
    """Later start times the meeting could move to today (ISO times)."""
    return {"slots": flight_data.meeting_slots(), "current_start": flight_data.meeting()["start"]}


@mcp.tool()
async def reschedule_meeting(start: str) -> dict:
    """Move the meeting to one of the slots from available_meeting_times. Only do this when the traveller
    has said yes to that time. Returns the updated meeting."""
    return flight_data.reschedule(start)


@mcp.tool()
async def update_dashboard(panel: Literal["flight", "weather", "meeting", "verdict", "route"], data: dict) -> dict:
    """Show information on the traveller's dashboard. Panels: flight, weather, meeting, verdict, and route
    (the trip from the airport to the meeting: `from` and `to` with lat/lon, `mode`, `minutes`).
    Returns `dashboard_url`: the link the traveller opens to see it."""
    entry: dict[str, Any] = {"ts": time.time(), "panel": panel, "data": data, "ok": False}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post(f"{DASHBOARD_URL}/api/state", json={"panel": panel, "data": data})
            r.raise_for_status()
        entry["ok"] = True
        public = os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8600").rstrip("/") + "/"
        result: dict[str, Any] = {"ok": True, "dashboard_url": public}
    except Exception as e:  # noqa: BLE001 — report any failure to the agent in plain words
        result = {"ok": False, "error": f"Couldn't reach the dashboard at {DASHBOARD_URL}: {e}"}
    DASHBOARD_HISTORY.append(entry)
    return result


@mcp.tool()
async def get_dashboard_history() -> list[dict]:
    """Every dashboard update sent since this server started (used by the factory's checker)."""
    return DASHBOARD_HISTORY


@mcp.custom_route("/reset", methods=["POST"])
async def reset(request: Request) -> JSONResponse:
    flight_data.reset()
    return JSONResponse({"ok": True})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
