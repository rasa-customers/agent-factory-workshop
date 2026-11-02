"""The workshop's mock world: one slightly troubled flight to New York, one meeting, and a few ways out.

The booked flight lands with only 5 minutes to spare by car. Two things can fix that: an alternate flight
into LaGuardia, or moving the meeting to a later slot. Everything here is deterministic except the time of
day (it's always "today" in New York), so the checker and the agent see the same world.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
CHI = ZoneInfo("America/Chicago")

AIRPORTS = {
    "JFK": {"code": "JFK", "name": "John F. Kennedy International", "lat": 40.6413, "lon": -73.7781},
    "LGA": {"code": "LGA", "name": "LaGuardia", "lat": 40.7769, "lon": -73.8740},
    "EWR": {"code": "EWR", "name": "Newark Liberty International", "lat": 40.6895, "lon": -74.1745},
}
MEETING_LOCATION = {"name": "1 Vanderbilt Ave", "lat": 40.7527, "lon": -73.9772}

# (airport, mode) -> (minutes to 1 Vanderbilt Ave, how)
TRAVEL = {
    ("JFK", "car"): (55, "Taxi or rideshare via the Van Wyck; midday traffic."),
    ("JFK", "subway"): (75, "AirTrain to Jamaica, then the E train; reliable but slower."),
    ("LGA", "car"): (35, "Taxi via the Grand Central Parkway; the closest airport to Midtown."),
    ("LGA", "subway"): (50, "Q70 bus to Jackson Heights, then the 7 train to Grand Central."),
    ("EWR", "car"): (60, "Taxi through the Lincoln Tunnel; tolls and tunnel traffic."),
    ("EWR", "subway"): (65, "AirTrain and NJ Transit to Penn Station, then the subway."),
}

_meeting_start: str | None = None  # set when the meeting is rescheduled; reset() puts it back


def _today() -> date:
    return datetime.now(NY).date()


def _at(tz: ZoneInfo, hh: int, mm: int) -> str:
    return datetime.combine(_today(), time(hh, mm), tz).isoformat()


def airport(name: str) -> str:
    """Which airport a free-text origin means; JFK unless it says LaGuardia or Newark."""
    low = name.lower()
    if "lga" in low or "laguardia" in low or "la guardia" in low:
        return "LGA"
    if "ewr" in low or "newark" in low:
        return "EWR"
    return "JFK"


def flight() -> dict:
    scheduled = datetime.combine(_today(), time(12, 35), NY)
    return {
        "flight_number": "RA 2026",
        "airline": "Rasa Air",
        "origin": "ORD",
        "destination": "JFK",
        "scheduled_departure": _at(CHI, 9, 15),
        "scheduled_arrival": scheduled.isoformat(),
        "estimated_arrival": (scheduled + timedelta(minutes=40)).isoformat(),
        "delay_minutes": 40,
        "status": "Delayed",
        "gate": "B22",
        "previous_gate": "B14",
        "terminal": "4",
    }


def alternate_flights() -> list[dict]:
    def alt(number, airline, code, dep, arr, seats, status):
        return {"flight_number": number, "airline": airline, "origin": "ORD", "arrival_airport": code,
                "departs": _at(CHI, *dep),
                "estimated_arrival": _at(NY, *arr), "seats_left": seats, "status": status}
    return [alt("RA 2030", "Rasa Air", "LGA", (10, 5), (12, 55), 4, "On time"),
            alt("SK 418", "Skyline", "EWR", (10, 20), (13, 35), 2, "On time"),
            alt("RA 2048", "Rasa Air", "JFK", (11, 0), (14, 5), 9, "On time")]


def meeting_slots() -> list[str]:
    return [_at(NY, 14, 45), _at(NY, 15, 0), _at(NY, 15, 30)]


def meeting() -> dict:
    return {"title": "Partner review", "start": _meeting_start or _at(NY, 14, 30),
            "address": "1 Vanderbilt Ave, New York, NY"}


def reschedule(start: str) -> dict:
    """Move the meeting to one of meeting_slots(); accepts an ISO time or a clock time like "14:45"."""
    global _meeting_start
    try:
        when = datetime.fromisoformat(start)
        if when.tzinfo is None:
            when = when.replace(tzinfo=NY)
    except ValueError:
        try:
            when = datetime.combine(_today(), time.fromisoformat(start.strip()), NY)
        except ValueError:
            when = None
    for slot in meeting_slots():
        if when is not None and datetime.fromisoformat(slot) == when:
            _meeting_start = slot
            return {"ok": True, "meeting": meeting()}
    return {"ok": False, "error": "That time isn't free. Use one of the slots from available_meeting_times."}


def reset() -> None:
    global _meeting_start
    _meeting_start = None
