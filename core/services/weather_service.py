"""
core/services/weather_service.py — Open-Meteo integration for WePet MVP.
Final corrected version for Django migration.
- Supports both city-based and coordinate-based weather fetch
- Preserves existing field names used across the system
- Safe against None geocoding
- NGO-compatible with stored GPS coordinates
"""

import requests
from datetime import datetime
from typing import Optional

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "wind_speed_10m",
    "uv_index",
    "is_day",
    "weather_code",
]

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "uv_index",
    "is_day",
]

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight showers",
    81: "Moderate showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
}


def _fmt_hour(time_str: str) -> str:
    """Format Open-Meteo hour string into readable label."""
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        try:
            dt = datetime.strptime(time_str[:13], "%Y-%m-%dT%H")
            return dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return time_str


def geocode_location(city: str) -> Optional[dict]:
    """
    Resolve city name → lat/lon/name via Open-Meteo Geocoding.
    Returns:
      - dict with location data
      - dict with {"error": "..."} on request failure
      - None if no results
    """
    if not city or not str(city).strip():
        return None

    try:
        resp = requests.get(
            GEOCODING_URL,
            params={
                "name": city.strip(),
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        if not results:
            return None

        r = results[0]

        name = r.get("name", city)
        admin1 = r.get("admin1", "")
        country = r.get("country", "")

        parts = [p for p in [name, admin1, country] if p]
        display = ", ".join(parts) if parts else city

        return {
            "name": name,
            "country": country,
            "admin1": admin1,
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "display": display,
        }

    except requests.RequestException as e:
        return {"error": f"Geocoding failed: {str(e)}"}


def fetch_weather(lat: float, lon: float) -> dict:
    """
    Fetch current conditions + next ~12 hours hourly forecast from Open-Meteo.
    IMPORTANT:
    Returns keys aligned with your existing system:
      current:
        temperature
        humidity
        apparent_temperature
        wind_speed
        uv_index
        is_day
        weather_code
        condition
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {"error": "Invalid coordinates."}

    try:
        resp = requests.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": ",".join(CURRENT_VARS),
                "hourly": ",".join(HOURLY_VARS),
                "forecast_days": 2,
                "timezone": "auto",
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()

        current_raw = raw.get("current", {})
        current = {
            "temperature": current_raw.get("temperature_2m"),
            "humidity": current_raw.get("relative_humidity_2m"),
            "apparent_temperature": current_raw.get("apparent_temperature"),
            "wind_speed": current_raw.get("wind_speed_10m"),
            "uv_index": current_raw.get("uv_index", 0) or 0,
            "is_day": current_raw.get("is_day", 1),
            "weather_code": current_raw.get("weather_code", 0),
            "condition": WEATHER_CODES.get(current_raw.get("weather_code", 0), "Unknown"),
        }

        hourly_raw = raw.get("hourly", {})
        times = hourly_raw.get("time", [])

        now_str = datetime.now().strftime("%Y-%m-%dT%H")
        hourly = []

        start_idx = 0
        for i, t in enumerate(times):
            if t.startswith(now_str):
                start_idx = i
                break

        temp_list = hourly_raw.get("temperature_2m", [])
        humidity_list = hourly_raw.get("relative_humidity_2m", [])
        apparent_list = hourly_raw.get("apparent_temperature", [])
        uv_list = hourly_raw.get("uv_index", [])
        is_day_list = hourly_raw.get("is_day", [])

        for i in range(start_idx, min(start_idx + 13, len(times))):
            hourly.append({
                "time": times[i],
                "hour_label": _fmt_hour(times[i]),
                "temperature": temp_list[i] if i < len(temp_list) else None,
                "humidity": humidity_list[i] if i < len(humidity_list) else None,
                "apparent_temperature": apparent_list[i] if i < len(apparent_list) else None,
                "uv_index": uv_list[i] if i < len(uv_list) else 0,
                "is_day": is_day_list[i] if i < len(is_day_list) else 1,
            })

        return {
            "current": current,
            "hourly": hourly,
        }

    except requests.RequestException as e:
        return {"error": f"Weather fetch failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected weather error: {str(e)}"}


def get_weather_for_location(city: str) -> dict:
    """
    Full pipeline:
      city → geocode → weather
    Used by pet owner + community + fallback NGO mode.
    """
    geo = geocode_location(city)

    if not geo:
        return {"error": "Location not found. Please try a different city name."}

    if not isinstance(geo, dict):
        return {"error": "Could not resolve the location. Please try again."}

    if "error" in geo:
        return {"error": geo.get("error", "Location not found. Please try a different city name.")}

    weather = fetch_weather(geo["latitude"], geo["longitude"])

    if not weather:
        return {"error": "Weather data unavailable. Please try again."}

    if not isinstance(weather, dict):
        return {"error": "Unexpected weather response."}

    if "error" in weather:
        return {"error": weather.get("error", "Weather data unavailable. Please try again.")}

    return {
        "location": geo,
        "current": weather["current"],
        "hourly": weather["hourly"],
    }


def get_weather_for_coordinates(lat: float, lon: float) -> dict:
    """
    Direct pipeline:
      lat/lon → weather
    BEST PATH for NGO shelters because GPS coordinates are persisted.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {"error": "Invalid shelter coordinates."}

    weather = fetch_weather(lat, lon)

    if not weather:
        return {"error": "Could not fetch weather for the saved shelter coordinates."}

    if not isinstance(weather, dict):
        return {"error": "Unexpected weather response."}

    if "error" in weather:
        return {"error": weather.get("error", "Weather data unavailable. Please try again.")}

    return {
        "location": {
            "name": "Current Location",
            "country": "",
            "admin1": "",
            "latitude": lat,
            "longitude": lon,
            "display": f"{lat:.4f}, {lon:.4f}",
        },
        "current": weather["current"],
        "hourly": weather["hourly"],
    }


def apply_location_display(weather_data: dict, display_label: str) -> dict:
    """
    Replace raw lat/lon display with a human-readable label
    after browser reverse geocoding.
    """
    if isinstance(weather_data, dict) and "error" not in weather_data:
        if "location" in weather_data and isinstance(weather_data["location"], dict):
            weather_data["location"]["display"] = display_label
    return weather_data