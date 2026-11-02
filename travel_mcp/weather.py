"""Real weather from Open-Meteo (no key), with a labelled fallback for bad Wi-Fi."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 4.0
REUSE_S = 1800  # one forecast per place for 30 minutes, so the agent and the checker see the same weather
FORECASTS: dict[str, tuple[float, dict, dict]] = {}

# WMO weather interpretation codes → short words
WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain",
       65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
       81: "Rain showers", 82: "Violent rain showers", 95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"}


def _sample(location: str, at: str) -> dict:
    return {"location": location, "at": at, "temperature_c": 9.0, "condition": "Overcast",
            "precipitation_mm": 0.0, "wind_kph": 14.0, "source": "cached-sample"}


# The workshop's trip lands in New York: every name for it gets the same forecast, so the agent saying
# "JFK" and the checker saying "New York" can't see different weather.
NEW_YORK = ("new york", "nyc", "jfk", "john f. kennedy", "john f kennedy", "kennedy", "lga", "laguardia",
            "la guardia", "ewr", "newark", "manhattan", "brooklyn", "queens", "midtown")


def _place_name(location: str) -> str:
    low = location.strip().lower()
    return "New York" if any(n in low for n in NEW_YORK) else location.strip()


async def _forecast(location: str) -> tuple[dict, dict]:
    location = _place_name(location)
    key = location.lower()
    hit = FORECASTS.get(key)
    if hit and time.monotonic() - hit[0] < REUSE_S:
        return hit[1], hit[2]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        geo = (await client.get(GEO_URL, params={"name": location, "count": 1})).json()
        place = geo["results"][0]
        fc = (await client.get(FORECAST_URL, params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "hourly": "temperature_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto"})).json()
    FORECASTS[key] = (time.monotonic(), place, fc)
    return place, fc


async def get_weather(location: str, at: str) -> dict:
    try:
        place, fc = await _forecast(location)
        when = datetime.fromisoformat(at)
        if when.tzinfo is not None and "utc_offset_seconds" in fc:  # no offset: already local at the destination
            when = when.astimezone(timezone(timedelta(seconds=fc["utc_offset_seconds"])))
        when = when.replace(tzinfo=None)
        h = fc["hourly"]
        times = [datetime.fromisoformat(t) for t in h["time"]]
        i = min(range(len(times)), key=lambda k: abs(times[k] - when))
        return {"location": place.get("name", location), "at": at,
                "temperature_c": float(h["temperature_2m"][i]),
                "condition": WMO.get(int(h["weather_code"][i]), "Unknown"),
                "precipitation_mm": float(h["precipitation"][i]),
                "wind_kph": float(h["wind_speed_10m"][i]), "source": "open-meteo"}
    except Exception:
        return _sample(location, at)
