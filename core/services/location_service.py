"""
core/services/location_service.py — Location utilities for WePet (Django edition).
Browser geolocation is handled by frontend JS; this module provides reverse geocoding.
Migrated from services/location_service.py — streamlit_js_eval removed; reverse geocode unchanged.
"""
import requests
from typing import Optional, Dict, Any


def reverse_geocode_osm(lat: float, lon: float) -> Dict[str, Any]:
    """
    Reverse geocode lat/lon using OpenStreetMap Nominatim.
    Returns dict with 'display' key for human-readable location label.
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {"User-Agent": "WePet/1.0 (pet-weather-risk-app)"}
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "zoom": 12,
        "addressdetails": 1,
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        address = data.get("address", {})
        parts = []

        locality = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("suburb")
            or address.get("county")
        )
        state = address.get("state")
        country = address.get("country")

        if locality:
            parts.append(locality)
        if state and state not in parts:
            parts.append(state)
        if country and country not in parts:
            parts.append(country)

        display = ", ".join(parts) if parts else data.get("display_name", "Current Location")
        return {"display": display}

    except Exception:
        return {"display": "Current Location"}