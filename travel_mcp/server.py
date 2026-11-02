"""Travel tools for the workshop, served over MCP on :8700.

Mock flight + meeting, real weather, and a bridge that pushes facts onto the dashboard.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

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
    """Estimate door-to-door travel time from an airport to an address, by car or subway.
    Returns the minutes and `arrives_at`: the clock time you'd arrive if you leave at depart_at."""
    minutes, note = flight_data.TRAVEL_MINUTES[mode]
    try:
        arrives_at = (datetime.fromisoformat(depart_at) + timedelta(minutes=minutes)).isoformat()
    except ValueError:
        arrives_at = None
    return {"minutes": minutes, "mode": mode, "arrives_at": arrives_at, "note": note}


@mcp.tool()
async def update_dashboard(panel: Literal["flight", "weather", "meeting", "verdict"], data: dict) -> dict:
    """Show information on the traveller's dashboard. Panels: flight, weather, meeting, verdict."""
    entry: dict[str, Any] = {"ts": time.time(), "panel": panel, "data": data, "ok": False}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post(f"{DASHBOARD_URL}/api/state", json={"panel": panel, "data": data})
            r.raise_for_status()
        entry["ok"] = True
        result: dict[str, Any] = {"ok": True}
    except Exception as e:  # noqa: BLE001 — report any failure to the agent in plain words
        result = {"ok": False, "error": f"Couldn't reach the dashboard at {DASHBOARD_URL}: {e}"}
    DASHBOARD_HISTORY.append(entry)
    return result


@mcp.tool()
async def get_dashboard_history() -> list[dict]:
    """Every dashboard update sent since this server started (used by the factory's checker)."""
    return DASHBOARD_HISTORY


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
