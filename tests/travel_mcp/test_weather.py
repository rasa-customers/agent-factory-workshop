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
