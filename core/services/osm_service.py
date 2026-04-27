"""
core/services/osm_service.py — OpenStreetMap Overpass API integration for WePet MVP.
Fetches nearby animal shelters and veterinary clinics by city name.
"""
import re
import requests


def clean_text(value: str) -> str:
    """Strip HTML tags from a string and collapse leftover whitespace."""
    if not value:
        return value
    no_tags = re.sub(r"<[^>]+>", "", value)
    return " ".join(no_tags.split()).strip()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "WePetMVP/1.0 (climate risk app for pets)"
}


def _geocode_city(city: str) -> tuple[float, float] | None:
    """Resolve city name to lat/lon using Nominatim."""
    try:
        resp = requests.get(
            GEOCODING_URL,
            params={"q": city, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        r = results[0]
        return float(r["lat"]), float(r["lon"])
    except Exception:
        return None


def _build_query(lat: float, lon: float, radius_m: int = 15000) -> str:
    """Build Overpass QL query for animal shelters and vets within radius."""
    return f"""
[out:json][timeout:20];
(
  node["amenity"="animal_shelter"](around:{radius_m},{lat},{lon});
  way["amenity"="animal_shelter"](around:{radius_m},{lat},{lon});
  node["amenity"="veterinary"](around:{radius_m},{lat},{lon});
  way["amenity"="veterinary"](around:{radius_m},{lat},{lon});
);
out center tags;
"""


def _parse_element(el: dict) -> dict:
    tags = el.get("tags", {})

    name = tags.get("name") or tags.get("name:en") or "Unknown Shelter"

    # Build address from available parts
    addr_parts = []
    for key in ["addr:housenumber", "addr:street", "addr:suburb", "addr:city", "addr:state"]:
        val = tags.get(key)
        if val:
            addr_parts.append(val)
    address = ", ".join(addr_parts) if addr_parts else "Address not available"

    # Get coordinates
    if el.get("type") == "way":
        center = el.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")
    else:
        lat = el.get("lat")
        lon = el.get("lon")

    amenity = tags.get("amenity", "animal_shelter")
    kind = "Veterinary Clinic" if amenity == "veterinary" else "Animal Shelter"

    phone = clean_text(tags.get("phone") or tags.get("contact:phone") or "")
    website = clean_text(tags.get("website") or tags.get("contact:website") or "")

    return {
        "name": name,
        "address": address,
        "lat": lat,
        "lon": lon,
        "kind": kind,
        "phone": phone,
        "website": website,
        "description": "Provides animal care and rescue services",
        "animals": "Dogs, Cats",
    }


def fetch_nearby_shelters(city: str) -> dict:
    """
    Main entry point. Returns dict with:
      - results: list of shelter dicts
      - error: str or None
      - count: int
    """
    coords = _geocode_city(city)
    if not coords:
        return {"results": [], "error": f"Could not locate '{city}'. Try a more specific city name.", "count": 0}

    lat, lon = coords

    try:
        query = _build_query(lat, lon)
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers=HEADERS,
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        return {"results": [], "error": "Request timed out. Please try again.", "count": 0}
    except Exception as e:
        return {"results": [], "error": f"Unable to fetch shelter data: {str(e)}", "count": 0}

    elements = data.get("elements", [])
    if not elements:
        return {"results": [], "error": None, "count": 0}

    seen_names = set()
    results = []
    for el in elements:
        parsed = _parse_element(el)
        # Deduplicate by name
        key = parsed["name"].lower()
        if key not in seen_names:
            seen_names.add(key)
            results.append(parsed)

    # Sort: shelters first, then vets; then alphabetically
    results.sort(key=lambda r: (0 if r["kind"] == "Animal Shelter" else 1, r["name"]))

    return {"results": results[:20], "error": None, "count": len(results)}