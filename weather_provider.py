from __future__ import annotations

import json
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen

from ai.config import combined_environment

WU_CURRENT_URL = "https://api.weather.com/v2/pws/observations/current"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "MavisDigitalCampus/0.9.7 (nonprofit planning weather client)"


def _api_key() -> str:
    # Use the same merged .env + process environment source as the AI providers.
    # Earlier weather builds looked only at os.environ, so a key saved in the
    # Campus .env file could incorrectly appear "not configured".
    values = combined_environment()
    return (
        values.get("WEATHER_UNDERGROUND_API_KEY", "").strip()
        or values.get("WUNDERGROUND_API_KEY", "").strip()
        or values.get("WEATHER_COM_API_KEY", "").strip()
    )


def weather_underground_key_available() -> bool:
    return bool(_api_key())


def fetch_json(url: str, params: dict[str, Any], timeout: float = 15.0, attempts: int = 2) -> dict[str, Any]:
    clean = {k: v for k, v in params.items() if v is not None}
    request = Request(f"{url}?{urlencode(clean)}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed trusted weather endpoints only
                payload = response.read(2_000_000)
            return json.loads(payload.decode("utf-8"))
        except (TimeoutError, socket.timeout, URLError) as exc:
            last_error = exc
            if attempt + 1 < max(1, attempts):
                time.sleep(0.35)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("Weather request failed before a response was received.")


def fetch_pws_current(station_id: str, timeout: float = 15.0) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise RuntimeError("Weather Underground API key is not configured.")
    data = fetch_json(
        WU_CURRENT_URL,
        {
            "stationId": station_id,
            "format": "json",
            "units": "e",
            "numericPrecision": "decimal",
            "apiKey": key,
        },
        timeout=timeout,
    )
    observations = data.get("observations") or []
    if not observations:
        raise RuntimeError(f"No current Weather Underground observation was returned for {station_id}.")
    obs = observations[0]
    imperial = obs.get("imperial") or {}
    return {
        "source": "Weather Underground PWS",
        "source_kind": "personal_weather_station",
        "station_id": obs.get("stationID") or station_id,
        "observed_at": obs.get("obsTimeUtc") or obs.get("obsTimeLocal") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "temperature_f": imperial.get("temp"),
        "feels_like_f": imperial.get("heatIndex") if imperial.get("heatIndex") is not None else imperial.get("windChill"),
        "humidity_pct": obs.get("humidity"),
        "dewpoint_f": imperial.get("dewpt"),
        "pressure_in": imperial.get("pressure"),
        "wind_mph": imperial.get("windSpeed"),
        "wind_gust_mph": imperial.get("windGust"),
        "wind_direction_deg": obs.get("winddir"),
        "precip_rate_in": imperial.get("precipRate"),
        "precip_total_in": imperial.get("precipTotal"),
        "solar_radiation": obs.get("solarRadiation"),
        "uv_index": obs.get("uv"),
        "latitude": obs.get("lat"),
        "longitude": obs.get("lon"),
        "summary": "Personal weather station observation",
    }


def _weather_code_summary(code: int | None) -> str:
    mapping = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
        56: "Light freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
        66: "Light freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Light rain showers", 81: "Rain showers", 82: "Heavy rain showers",
        85: "Light snow showers", 86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
        99: "Thunderstorm with heavy hail",
    }
    return mapping.get(code, "Weather conditions")


def fetch_open_meteo(latitude: float, longitude: float, timezone_name: str, timeout: float = 15.0) -> dict[str, Any]:
    data = fetch_json(
        OPEN_METEO_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_name,
            "forecast_days": 7,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "current": ",".join([
                "temperature_2m", "relative_humidity_2m", "apparent_temperature", "precipitation",
                "rain", "showers", "snowfall", "weather_code", "surface_pressure", "wind_speed_10m",
                "wind_direction_10m", "wind_gusts_10m",
            ]),
            "daily": ",".join([
                "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max",
                "precipitation_sum", "rain_sum", "snowfall_sum", "wind_speed_10m_max", "wind_gusts_10m_max",
                "sunrise", "sunset", "daylight_duration",
            ]),
        },
        timeout=timeout,
    )
    current = data.get("current") or {}
    current_result = {
        "source": "Open-Meteo",
        "source_kind": "model_fallback",
        "station_id": "",
        "observed_at": current.get("time") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "temperature_f": current.get("temperature_2m"),
        "feels_like_f": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "dewpoint_f": None,
        "pressure_in": (current.get("surface_pressure") / 33.8638866667) if current.get("surface_pressure") is not None else None,
        "wind_mph": current.get("wind_speed_10m"),
        "wind_gust_mph": current.get("wind_gusts_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "precip_rate_in": current.get("precipitation"),
        "precip_total_in": None,
        "solar_radiation": None,
        "uv_index": None,
        "latitude": data.get("latitude") or latitude,
        "longitude": data.get("longitude") or longitude,
        "summary": _weather_code_summary(current.get("weather_code")),
    }
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    forecasts: list[dict[str, Any]] = []
    for idx, day in enumerate(dates):
        def item(name: str):
            values = daily.get(name) or []
            return values[idx] if idx < len(values) else None
        forecasts.append({
            "forecast_date": day,
            "high_f": item("temperature_2m_max"),
            "low_f": item("temperature_2m_min"),
            "precip_chance": item("precipitation_probability_max"),
            "precip_total_in": item("precipitation_sum"),
            "rain_total_in": item("rain_sum"),
            "snow_total_in": item("snowfall_sum"),
            "wind_max_mph": item("wind_speed_10m_max"),
            "wind_gust_max_mph": item("wind_gusts_10m_max"),
            "sunrise": item("sunrise"),
            "sunset": item("sunset"),
            "daylight_seconds": item("daylight_duration"),
            "summary": _weather_code_summary(item("weather_code")),
            "source": "Open-Meteo",
        })
    return {"current": current_result, "forecast": forecasts}


def refresh_weather(settings: dict[str, Any]) -> dict[str, Any]:
    station_id = str(settings.get("pws_station_id") or "KWFLATT11").strip()
    latitude = settings.get("latitude")
    longitude = settings.get("longitude")
    timezone_name = str(settings.get("timezone_name") or "America/New_York")
    errors: list[str] = []
    pws = None
    if station_id and weather_underground_key_available():
        try:
            pws = fetch_pws_current(station_id)
        except Exception as exc:  # weather must fail soft
            errors.append(f"PWS: {exc}")
    elif station_id:
        errors.append("PWS: Weather Underground API key not configured")

    fallback = None
    if latitude is not None and longitude is not None:
        try:
            fallback = fetch_open_meteo(float(latitude), float(longitude), timezone_name)
        except Exception as exc:  # weather must fail soft
            errors.append(f"Forecast: {exc}")
    else:
        errors.append("Forecast: latitude/longitude not configured")

    current = pws or (fallback or {}).get("current")
    forecasts = (fallback or {}).get("forecast") or []
    if current is None and not forecasts:
        raise RuntimeError("; ".join(errors) or "No weather source returned data.")
    return {
        "current": current,
        "forecast": forecasts,
        "pws_connected": bool(pws),
        "pws_key_available": weather_underground_key_available(),
        "errors": errors,
    }
