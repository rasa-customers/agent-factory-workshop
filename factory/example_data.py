"""The workshop's example trip, sent to a freshly built dashboard so it comes to life straight away.
In Breakout 2 the travel agent takes over the same panels with what it finds."""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from travel_mcp import flight_data
from travel_mcp.weather import get_weather

NOTE = "Example data: your travel agent will fill this in during Breakout 2"
DEPLANE_MINUTES = 15


async def example_panels() -> dict[str, dict]:
    flight, meeting = flight_data.flight(), flight_data.meeting()
    weather = await get_weather("New York", flight["estimated_arrival"])
    car_minutes, _ = flight_data.TRAVEL[("JFK", "car")]
    arrive = (datetime.fromisoformat(flight["estimated_arrival"])
              + timedelta(minutes=DEPLANE_MINUTES + car_minutes))
    slack = int((datetime.fromisoformat(meeting["start"]) - arrive).total_seconds() // 60)
    status = "no" if slack < 0 else "tight" if slack < 15 else "yes"
    reason = (f"Landing at {datetime.fromisoformat(flight['estimated_arrival']):%H:%M}, "
              f"{DEPLANE_MINUTES} min to get off and {car_minutes} min by car puts you there at {arrive:%H:%M}.")
    return {
        "flight": {**flight, "note": NOTE},
        "weather": {**weather, "note": NOTE},
        "meeting": {**meeting, "note": NOTE},
        "verdict": {"status": status, "slack_minutes": slack, "reason": reason, "note": NOTE},
        "route": {"from": flight_data.AIRPORTS["JFK"], "to": flight_data.MEETING_LOCATION, "mode": "car",
                  "minutes": car_minutes, "note": NOTE},
    }


async def seed_dashboard(base_url: str) -> bool:
    """Send the example trip to every panel. Never raises: a dashboard without it still works."""
    try:
        panels = await example_panels()
        async with httpx.AsyncClient(timeout=5) as c:
            for panel, data in panels.items():
                (await c.post(f"{base_url.rstrip('/')}/api/state", json={"panel": panel, "data": data})).raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"could not send example data to the dashboard: {e}", flush=True)
        return False
