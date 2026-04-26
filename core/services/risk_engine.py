"""
core/services/risk_engine.py — Deterministic, explainable climate risk engine for WePet MVP.
Migrated from services/risk_engine.py — ZERO logic changes.
"""
from typing import Optional


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


# ─── Weather Pressure Normalizers ─────────────────────────────────────────────

def compute_pressures(weather: dict, breed: dict) -> dict:
    temp = weather["temperature"]
    apparent = weather["apparent_temperature"]
    humidity = weather["humidity"]
    uv = weather.get("uv_index", 0) or 0
    wind = weather.get("wind_speed", 0) or 0
    is_day = weather.get("is_day", 1)

    temp_pressure = clamp((temp - breed["thermal_comfort_max"]) / 12)
    apparent_pressure = clamp((apparent - breed["safe_apparent_temp_limit"]) / 10)
    humidity_pressure = clamp((humidity - 55) / 35)
    uv_pressure = clamp((uv - 3) / 8) if is_day else 0.0
    wind_relief = clamp(wind / 25, 0, 0.25)

    return {
        "temp_pressure": temp_pressure,
        "apparent_pressure": apparent_pressure,
        "humidity_pressure": humidity_pressure,
        "uv_pressure": uv_pressure,
        "wind_relief": wind_relief,
    }


# ─── Modifier Bonus ────────────────────────────────────────────────────────────

def compute_modifier_bonus(age_group: str, overweight: bool, heat_sensitive: bool) -> float:
    bonus = 0.0
    if age_group == "senior":
        bonus += 0.08
    if overweight:
        bonus += 0.10
    if heat_sensitive:
        bonus += 0.10
    return bonus


# ─── Sub-Scores ───────────────────────────────────────────────────────────────

def compute_heat_stress(pressures: dict, breed: dict, modifier_bonus: float) -> float:
    raw = (
        0.30 * pressures["temp_pressure"]
        + 0.35 * pressures["apparent_pressure"]
        + 0.20 * pressures["humidity_pressure"] * breed["humidity_sensitivity"]
        + 0.10 * pressures["uv_pressure"]
        + 0.15 * breed["base_heat_sensitivity"]
        + modifier_bonus
        - pressures["wind_relief"]
    )
    return clamp(raw) * 100


def compute_dehydration(pressures: dict, breed: dict, modifier_bonus: float) -> float:
    raw = (
        0.35 * pressures["temp_pressure"]
        + 0.25 * pressures["apparent_pressure"]
        + 0.20 * pressures["humidity_pressure"]
        + 0.10 * breed["dehydration_sensitivity"]
        + 0.10 * pressures["uv_pressure"]
        + modifier_bonus * 0.5
    )
    return clamp(raw) * 100


def compute_respiratory(pressures: dict, breed: dict, modifier_bonus: float) -> float:
    raw = (
        0.30 * pressures["apparent_pressure"]
        + 0.25 * pressures["humidity_pressure"]
        + 0.25 * breed["respiratory_sensitivity"]
        + 0.10 * pressures["uv_pressure"]
        + modifier_bonus * 0.4
    )
    return clamp(raw) * 100


def compute_surface_burn(pressures: dict, breed: dict, weather: dict) -> float:
    temp = weather["temperature"]
    uv = weather.get("uv_index", 0) or 0

    raw = (
        0.45 * pressures["temp_pressure"]
        + 0.25 * pressures["uv_pressure"]
        + 0.20 * pressures["apparent_pressure"]
        + 0.10 * breed["surface_burn_sensitivity"]
    )
    score = clamp(raw) * 100
    if temp >= 30 and uv >= 6:
        score = min(score + 10, 100)
    return score


def compute_indoor_heat(pressures: dict, breed: dict) -> float:
    raw = (
        0.35 * pressures["temp_pressure"]
        + 0.30 * pressures["apparent_pressure"]
        + 0.10 * pressures["humidity_pressure"]
        + 0.25 * breed["indoor_heat_trap_sensitivity"]
    )
    return clamp(raw) * 100


# ─── Overall Risk ─────────────────────────────────────────────────────────────

def compute_overall_risk(sub_scores: dict) -> float:
    return (
        0.32 * sub_scores["heat_stress"]
        + 0.18 * sub_scores["dehydration"]
        + 0.22 * sub_scores["respiratory"]
        + 0.14 * sub_scores["surface_burn"]
        + 0.14 * sub_scores["indoor_heat"]
    )


def risk_level_label(score: float) -> str:
    if score < 25:
        return "Low"
    elif score < 50:
        return "Moderate"
    elif score < 75:
        return "High"
    else:
        return "Critical"


# ─── Hidden Risk Drivers ──────────────────────────────────────────────────────

def compute_hidden_risk_drivers(weather: dict, breed: dict, sub_scores: dict) -> list:
    drivers = []
    temp = weather["temperature"]
    apparent = weather["apparent_temperature"]
    humidity = weather["humidity"]
    uv = weather.get("uv_index", 0) or 0
    is_day = weather.get("is_day", 1)
    species = breed["species_type"]
    coat = breed.get("coat_type", "")

    heat_stress = sub_scores.get("heat_stress", 0)
    respiratory = sub_scores.get("respiratory", 0)
    surface_burn = sub_scores.get("surface_burn", 0)
    indoor_heat = sub_scores.get("indoor_heat", 0)

    warm_context = (
        temp >= breed.get("heat_alert_threshold", 28) - 4
        or apparent >= breed.get("safe_apparent_temp_limit", 30) - 3
        or heat_stress >= 30
        or indoor_heat >= 30
    )

    hot_context = (
        temp >= breed.get("heat_alert_threshold", 28)
        or apparent >= breed.get("safe_apparent_temp_limit", 30)
        or heat_stress >= 45
    )

    if (
        humidity > 75
        and species == "dog"
        and (apparent >= 20 or heat_stress >= 25 or respiratory >= 35)
    ):
        drivers.append(
            "🌫️ High humidity reduces cooling efficiency through panting, making warm conditions feel harder than they appear."
        )

    if (apparent - temp >= 3) and (apparent >= 22 or heat_stress >= 25):
        drivers.append(
            f"🌡️ Apparent temperature ({apparent:.1f}°C) is notably higher than air temperature ({temp:.1f}°C), "
            "which can create hidden heat load."
        )

    if breed.get("brachycephalic", False) and (respiratory >= 35 or warm_context):
        drivers.append(
            "😮‍💨 Brachycephalic anatomy can make breathing strain appear earlier than expected in warm or humid conditions."
        )

    dense_coats = ["double_coat", "double_coat_heavy", "long_dense", "heavy_long", "dense_short"]
    if coat in dense_coats and (heat_stress >= 35 or indoor_heat >= 35 or hot_context):
        drivers.append(
            "🧣 Dense or insulating coat can slow cooling after activity, so heat may persist even after returning indoors."
        )

    if uv >= 6 and is_day:
        drivers.append(
            "☀️ Strong UV increases direct heat load and raises hot-surface risk, even when air temperature feels manageable."
        )

    if surface_burn >= 55:
        drivers.append(
            "🔥 Pavement and hard surfaces may be significantly hotter than the air — paw burn risk is elevated."
        )

    if indoor_heat >= 55 and species == "cat":
        drivers.append(
            "🏠 Sun-facing indoor spaces can trap heat surprisingly fast — indoor risk may exceed outdoor apparent conditions."
        )

    if breed["breed_name"] == "Sphynx" and uv >= 5 and is_day:
        drivers.append(
            "🦴 Sphynx skin is highly sun-sensitive — direct sunlight and window sun patches can raise risk quickly."
        )

    if breed["breed_name"] == "Siberian Husky" and (temp >= 22 or apparent >= 24 or heat_stress >= 35):
        drivers.append(
            "🐺 Cold-adapted breeds like Huskies can accumulate heat stress earlier than owners expect in mild-to-warm weather."
        )

    if not drivers and temp <= breed.get("thermal_comfort_max", 24) and heat_stress < 20:
        if species == "dog" and humidity >= 75:
            drivers.append(
                "🌥️ Conditions are generally comfortable right now. Humidity is elevated, so longer active sessions may still feel slightly heavier than expected."
            )
        elif coat in dense_coats:
            drivers.append(
                "🧥 Current conditions are generally comfortable for this coat type. If the coat gets wet, dry thoroughly after outdoor time to avoid lingering discomfort."
            )
        else:
            drivers.append(
                "✅ No major hidden heat drivers detected right now — current conditions appear generally manageable for this pet."
            )

    return drivers[:5]


# ─── Safe Window Logic ────────────────────────────────────────────────────────

def _hourly_risk_simplified(hour: dict, breed: dict) -> float:
    temp = hour.get("temperature") or 20
    apparent = hour.get("apparent_temperature") or temp
    humidity = hour.get("humidity") or 50
    uv = hour.get("uv_index") or 0
    is_day = hour.get("is_day", 1)

    temp_p = clamp((temp - breed["thermal_comfort_max"]) / 12)
    apparent_p = clamp((apparent - breed["safe_apparent_temp_limit"]) / 10)
    humidity_p = clamp((humidity - 55) / 35)
    uv_p = clamp((uv - 3) / 8) if is_day else 0

    raw = (
        0.35 * apparent_p
        + 0.25 * temp_p
        + 0.20 * humidity_p * breed["humidity_sensitivity"]
        + 0.10 * uv_p
        + 0.10 * breed["base_heat_sensitivity"]
    )
    return clamp(raw) * 100


def compute_safe_windows(hourly: list, breed: dict) -> dict:
    if not hourly:
        return {
            "windows": [],
            "message": "No forecast data available for window analysis.",
            "indoor_only": False,
        }

    scored = []
    for h in hourly:
        if h.get("temperature") is None:
            continue
        risk = _hourly_risk_simplified(h, breed)
        suitability = 100 - risk

        uv = h.get("uv_index") or 0
        apparent = h.get("apparent_temperature") or h.get("temperature")
        humidity = h.get("humidity") or 50
        is_day = h.get("is_day", 1)

        if uv > 5:
            suitability -= 8
        if apparent > breed["safe_apparent_temp_limit"]:
            suitability -= 12
        if humidity > 75 and breed["species_type"] == "dog":
            suitability -= 8
        if is_day and uv > 5:
            suitability -= 5

        scored.append({
            "time": h["time"],
            "hour_label": h["hour_label"],
            "suitability": suitability,
            "risk": risk,
            "apparent": apparent,
        })

    windows = []
    current_window = []

    for s in scored:
        if s["suitability"] >= 55:
            current_window.append(s)
        else:
            if current_window:
                windows.append(current_window)
                current_window = []
    if current_window:
        windows.append(current_window)

    windows.sort(key=lambda w: sum(h["risk"] for h in w) / len(w))
    top_windows = windows[:2]

    if not top_windows:
        return {
            "windows": [],
            "message": "No low-risk outdoor window detected in the next 12 hours. Indoor enrichment recommended.",
            "indoor_only": True,
        }

    formatted = []
    for w in top_windows:
        start = w[0]["hour_label"]
        end = w[-1]["hour_label"]
        avg_risk = sum(h["risk"] for h in w) / len(w)
        avg_apparent = sum(h["apparent"] for h in w) / len(w)
        label = f"{start}" if len(w) == 1 else f"{start} – {end}"
        formatted.append({
            "window": label,
            "avg_risk": avg_risk,
            "avg_apparent": avg_apparent,
            "hours": len(w),
        })

    return {
        "windows": formatted,
        "message": "Best window(s) identified from next 12-hour forecast.",
        "indoor_only": False,
    }


# ─── Max Outdoor Exposure ─────────────────────────────────────────────────────

def compute_max_exposure(
    risk_level: str,
    breed: dict,
    sub_scores: dict,
    age_group: str,
    overweight: bool,
    heat_sensitive: bool,
) -> dict:
    heat = sub_scores["heat_stress"]
    resp = sub_scores["respiratory"]
    surf = sub_scores["surface_burn"]
    indoor = sub_scores["indoor_heat"]

    base = {
        "Low": 60,
        "Moderate": 35,
        "High": 15,
        "Critical": 0,
    }.get(risk_level, 0)

    breed_penalty = 0
    if heat >= 35 or indoor >= 35:
        breed_penalty = int(breed["base_heat_sensitivity"] * 10)

    if resp >= 75:
        resp_penalty = 10
    elif resp >= 55:
        resp_penalty = 6
    elif resp >= 35:
        resp_penalty = 3
    else:
        resp_penalty = 0

    if surf >= 75:
        surf_penalty = 8
    elif surf >= 55:
        surf_penalty = 5
    elif surf >= 35:
        surf_penalty = 2
    else:
        surf_penalty = 0

    mod_penalty = 0
    if age_group.lower() == "senior":
        mod_penalty += 5
    if overweight:
        mod_penalty += 5
    if heat_sensitive:
        mod_penalty += 6

    final = max(base - breed_penalty - resp_penalty - surf_penalty - mod_penalty, 0)

    if final == 0:
        label = "🏠 Indoor-only today"
        desc = "Outdoor exposure is not recommended under current conditions except for essential needs."
    elif final <= 5:
        label = f"⏱️ Essential relief breaks only ({final} min)"
        desc = "Keep outings extremely brief, shaded, and closely supervised."
    elif final <= 15:
        label = f"⏱️ Very short controlled outdoor time ({final} min)"
        desc = "Limit activity strictly. Prioritize shade, water, and low exertion."
    elif final <= 30:
        label = f"⏱️ Short outdoor session ({final} min)"
        desc = "Manageable with water access, shade, and close observation."
    elif final <= 50:
        label = f"⏱️ Moderate outdoor activity possible ({final} min)"
        desc = "Generally manageable, but avoid intense exertion and monitor comfort."
    else:
        label = f"⏱️ Comfortable outdoor activity window ({final} min)"
        desc = "Conditions are generally suitable for routine outdoor time, with normal hydration and observation."

    return {"minutes": final, "label": label, "description": desc}


# ─── Community Heat Score ─────────────────────────────────────────────────────

def compute_community_heat_score(weather: dict) -> dict:
    temp = weather["temperature"]
    apparent = weather["apparent_temperature"]
    humidity = weather["humidity"]
    uv = weather.get("uv_index", 0) or 0
    is_day = weather.get("is_day", 1)

    temp_p = clamp((temp - 22) / 12)
    apparent_p = clamp((apparent - 28) / 10)
    humidity_p = clamp((humidity - 55) / 35)
    uv_p = clamp((uv - 3) / 8) if is_day else 0

    score = (
        0.35 * temp_p
        + 0.35 * apparent_p
        + 0.15 * humidity_p
        + 0.15 * uv_p
    ) * 100

    score = clamp(score, 0, 100)
    label = risk_level_label(score)

    return {"score": score, "level": label}


# ─── NGO Distress Severity ────────────────────────────────────────────────────

SYMPTOM_WEIGHTS = {
    "heavy_panting": 20,
    "lethargy": 15,
    "collapse": 40,
    "unable_to_stand": 35,
    "open_mouth_breathing": 25,
    "disorientation": 25,
}

WEATHER_BONUS = {"Low": 0, "Moderate": 5, "High": 10, "Critical": 15}
ANIMAL_BONUS = {"dog": 5, "cat": 3, "unknown": 0}

URGENCY_TEXT = {
    "Low": "Monitor / low-priority follow-up",
    "Moderate": "Needs review soon",
    "High": "Prioritize response",
    "Critical": "🚨 Urgent response recommended",
}


def compute_distress_severity(symptoms: list, animal_type: str, weather_level: str) -> dict:
    sym_score = sum(SYMPTOM_WEIGHTS.get(s, 0) for s in symptoms)
    weather_bonus = WEATHER_BONUS.get(weather_level, 0)
    animal_bonus = ANIMAL_BONUS.get(animal_type.lower(), 0)

    score = min(sym_score + weather_bonus + animal_bonus, 100)
    level = risk_level_label(score)
    urgency = URGENCY_TEXT.get(level, "")

    return {"score": score, "level": level, "urgency": urgency}

# ─── NGO Group Risk Helper ─────────────────────────────────────────────────────

def compute_ngo_group_risk(weather: dict, breed: dict) -> dict:
    """
    Lightweight NGO wrapper over the existing pet risk engine.
    Uses default NGO-safe assumptions for group-level monitoring.
    """
    pressures = compute_pressures(weather, breed)
    modifier_bonus = compute_modifier_bonus(
        age_group="adult",
        overweight=False,
        heat_sensitive=breed.get("base_heat_sensitivity", 0) >= 0.7
    )

    sub_scores = {
        "heat_stress": compute_heat_stress(pressures, breed, modifier_bonus),
        "dehydration": compute_dehydration(pressures, breed, modifier_bonus),
        "respiratory": compute_respiratory(pressures, breed, modifier_bonus),
        "surface_burn": compute_surface_burn(pressures, breed, weather),
        "indoor_heat": compute_indoor_heat(pressures, breed),
    }

    overall = compute_overall_risk(sub_scores)
    risk_level = risk_level_label(overall)

    recommendations = []
    watch_signs = []

    if risk_level == "Critical":
        recommendations = [
            "Move this group to coolest shaded/ventilated area immediately.",
            "Provide continuous clean water access.",
            "Avoid all outdoor exposure except emergency handling.",
        ]
        watch_signs = [
            "Heavy panting",
            "Lethargy",
            "Collapse",
            "Disorientation",
        ]
    elif risk_level == "High":
        recommendations = [
            "Limit outdoor activity and reduce handling stress.",
            "Increase hydration checks and shade access.",
            "Monitor this group more frequently.",
        ]
        watch_signs = [
            "Panting",
            "Reduced activity",
            "Warm ears/paws",
            "Seeking cooler surfaces",
        ]
    elif risk_level == "Moderate":
        recommendations = [
            "Ensure shade, airflow, and water availability.",
            "Avoid peak-heat exposure if possible.",
        ]
        watch_signs = [
            "Mild panting",
            "Restlessness",
        ]
    else:
        recommendations = [
            "Conditions currently manageable with routine monitoring.",
        ]
        watch_signs = [
            "No major heat warning signs expected right now.",
        ]

    reason = (
        f"Heat stress {sub_scores['heat_stress']:.1f}, "
        f"respiratory {sub_scores['respiratory']:.1f}, "
        f"dehydration {sub_scores['dehydration']:.1f}"
    )

    return {
        "risk_score": round(overall, 1),
        "risk_level": risk_level,
        "recommendations": recommendations,
        "watch_signs": watch_signs,
        "reason": reason,
        "sub_scores": sub_scores,
    }