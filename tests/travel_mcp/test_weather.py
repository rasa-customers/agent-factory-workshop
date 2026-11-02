import httpx

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FC = "https://api.open-meteo.com/v1/forecast"


async def test_get_weather_uses_open_meteo(call, respx_mock):
    respx_mock.get(GEO).mock(return_value=httpx.Response(200, json={"results": [{"name": "New York", "latitude": 40.7, "longitude": -74.0}]}))
    respx_mock.get(FC).mock(return_value=httpx.Response(200, json={"hourly": {
        "time": ["2026-11-03T12:00", "2026-11-03T13:00", "2026-11-03T14:00"],
        "temperature_2m": [9.0, 10.5, 11.0], "precipitation": [0.0, 0.4, 0.0],
        "weather_code": [3, 61, 2], "wind_speed_10m": [12.0, 15.0, 10.0]}}))
    w = await call("get_weather", {"location": "New York", "at": "2026-11-03T13:15:00-05:00"})
    assert w["source"] == "open-meteo"
    assert w["temperature_c"] == 10.5 and w["condition"] == "Light rain"


async def test_get_weather_falls_back_on_network_error(call, respx_mock):
    respx_mock.get(GEO).mock(side_effect=httpx.ConnectError("no wifi"))
    w = await call("get_weather", {"location": "New York", "at": "2026-11-03T13:15:00-05:00"})
    assert w["source"] == "cached-sample" and isinstance(w["temperature_c"], float)


def _forecast(codes):
    return httpx.Response(200, json={"utc_offset_seconds": -18000, "hourly": {
        "time": ["2026-11-03T12:00", "2026-11-03T13:00", "2026-11-03T14:00"],
        "temperature_2m": [9.0, 10.5, 11.0], "precipitation": [0.0, 0.4, 0.0],
        "weather_code": codes, "wind_speed_10m": [12.0, 15.0, 10.0]}})


async def test_a_time_without_offset_means_local_time_at_the_destination(call, respx_mock, monkeypatch):
    import time
    monkeypatch.setenv("TZ", "UTC")  # cloud machines run in UTC
    time.tzset()
    respx_mock.get(GEO).mock(return_value=httpx.Response(200, json={"results": [{"name": "New York", "latitude": 40.7, "longitude": -74.0}]}))
    respx_mock.get(FC).mock(return_value=_forecast([3, 61, 2]))
    w = await call("get_weather", {"location": "New York", "at": "2026-11-03T13:15:00"})
    assert w["condition"] == "Light rain"


async def test_the_agent_and_the_checker_see_the_same_forecast(call, respx_mock):
    respx_mock.get(GEO).mock(return_value=httpx.Response(200, json={"results": [{"name": "New York", "latitude": 40.7, "longitude": -74.0}]}))
    fc = respx_mock.get(FC).mock(side_effect=[_forecast([3, 61, 2]), _forecast([0, 0, 0])])
    first = await call("get_weather", {"location": "New York", "at": "2026-11-03T13:15:00-05:00"})
    second = await call("get_weather", {"location": "new york", "at": "2026-11-03T13:20:00-05:00"})
    assert first["condition"] == second["condition"] == "Light rain"
    assert fc.call_count == 1


async def test_airport_and_city_names_share_one_forecast(call, respx_mock):
    geo = respx_mock.get(GEO).mock(return_value=httpx.Response(200, json={"results": [{"name": "New York", "latitude": 40.7, "longitude": -74.0}]}))
    respx_mock.get(FC).mock(return_value=_forecast([3, 61, 2]))
    names = ["New York", "JFK", "JFK Airport", "NYC", "New York, NY", "Manhattan", "LaGuardia"]
    results = [await call("get_weather", {"location": n, "at": "2026-11-03T13:15:00-05:00"}) for n in names]
    assert {r["condition"] for r in results} == {"Light rain"}
    assert geo.call_count == 1 and geo.calls[0].request.url.params["name"] == "New York"
