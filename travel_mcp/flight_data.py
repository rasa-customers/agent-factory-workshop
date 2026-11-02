"""The workshop's mock world: one slightly troubled flight to New York and one meeting."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
CHI = ZoneInfo("America/Chicago")


def _today() -> date:
    return datetime.now(NY).date()


def _at(tz: ZoneInfo, hh: int, mm: int) -> str:
    return datetime.combine(_today(), time(hh, mm), tz).isoformat()


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


def meeting() -> dict:
    return {"title": "Partner review", "start": _at(NY, 14, 30), "address": "1 Vanderbilt Ave, New York, NY"}


TRAVEL_MINUTES = {"car": (55, "Taxi or rideshare via the Van Wyck; midday traffic."),
                  "subway": (75, "AirTrain to Jamaica, then the E train; reliable but slower.")}
