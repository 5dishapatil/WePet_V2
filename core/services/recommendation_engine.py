"""
core/services/recommendation_engine.py — Dynamic, breed-specific, justified recommendations.
Migrated from services/recommendation_engine.py — ZERO logic changes.
"""
from core.services.risk_engine import clamp


def generate_recommendations(
    breed: dict,
    weather: dict,
    sub_scores: dict,
    overall_risk: float,
    risk_level: str,
    age_group: str,
    overweight: bool,
    heat_sensitive: bool,
) -> list:
    recs = []
    dehydration = sub_scores["dehydration"]
    respiratory = sub_scores["respiratory"]
    heat_stress = sub_scores["heat_stress"]
    indoor_heat = sub_scores["indoor_heat"]
    breed_name = breed["breed_name"]
    species = breed["species_type"]
    uv = weather.get("uv_index", 0) or 0
    is_day = weather.get("is_day", 1)

    # ─── Hydration ───────────────────────────────────────────────────────────
    if dehydration >= 60:
        recs.append({
            "category": "Hydration",
            "icon": "💧",
            "advice": "Offer cool fresh water before and immediately after any outing. "
                      "Refresh the bowl frequently — warm water is less enticing.",
            "why": "Elevated dehydration pressure from combined heat and humidity load.",
        })
    elif dehydration >= 40:
        recs.append({
            "category": "Hydration",
            "icon": "💧",
            "advice": "Keep extra water accessible and encourage frequent small drinks throughout the day.",
            "why": "Moderate dehydration risk detected — maintaining hydration is preventive.",
        })

    # ─── Activity Level ───────────────────────────────────────────────────────
    if risk_level == "Critical":
        recs.append({
            "category": "Activity",
            "icon": "🚫",
            "advice": "Indoor-only recommended today except for essential relief breaks if applicable. "
                      "No play, exercise, or extended outdoor time.",
            "why": "Overall risk is Critical — outdoor exertion creates serious heat stress risk for this breed.",
        })
    elif risk_level == "High":
        recs.append({
            "category": "Activity",
            "icon": "⚠️",
            "advice": "Avoid exercise-based outings. Only brief, necessary outdoor exposure in full shade.",
            "why": "High overall risk makes sustained outdoor activity unsafe for this breed under current conditions.",
        })
    elif risk_level == "Moderate":
        recs.append({
            "category": "Activity",
            "icon": "🔶",
            "advice": "Keep outdoor sessions short and strictly timed. Prioritize early morning or post-sunset.",
            "why": "Moderate risk — manageable with close monitoring and strict time limits.",
        })

    # ─── Breed-Specific: Pug ─────────────────────────────────────────────────
    if breed_name == "Pug":
        if respiratory >= 60:
            recs.append({
                "category": "Breed Alert",
                "icon": "😮‍💨",
                "advice": "Avoid any exertion even during short outings. Breathing strain can escalate "
                          "rapidly in Pugs due to their shortened airway structure.",
                "why": "Brachycephalic anatomy severely limits heat dissipation via panting.",
            })
        if indoor_heat >= 40:
            recs.append({
                "category": "Indoor Care",
                "icon": "🏠",
                "advice": "Ensure air conditioning or strong airflow in all resting areas. "
                          "Pugs cannot tolerate indoor heat accumulation.",
                "why": "Shortened airway means indoor thermal comfort is as critical as outdoor management.",
            })

    # ─── Breed-Specific: Husky ───────────────────────────────────────────────
    if breed_name == "Siberian Husky":
        if heat_stress >= 55:
            recs.append({
                "category": "Breed Alert",
                "icon": "🐺",
                "advice": "Keep activity minimal and strictly shaded. Do not trust visible comfort cues — "
                          "Huskies can accumulate dangerous internal heat before showing obvious signs.",
                "why": "Cold-adapted double coat raises hidden heat burden well above what ambient temperature suggests.",
            })

    # ─── Dense Coat Breeds ───────────────────────────────────────────────────
    dense_coats = ["double_coat", "double_coat_heavy", "long_dense", "heavy_long"]
    if breed.get("coat_type") in dense_coats and heat_stress >= 40:
        recs.append({
            "category": "Post-Activity",
            "icon": "🛏️",
            "advice": "Use a cooling mat or damp towel on a tile surface after any outdoor activity. "
                      "Allow minimum 20 minutes of cool rest before any further exertion.",
            "why": "Dense coat continues retaining heat after the outing ends — post-activity cooling is as important as pre-activity prep.",
        })

    # ─── Persian ─────────────────────────────────────────────────────────────
    if breed_name == "Persian":
        if indoor_heat >= 55:
            recs.append({
                "category": "Indoor Care",
                "icon": "🏠",
                "advice": "Prioritize airflow and cool indoor rest zones. Block sun-facing windows during "
                          "peak hours. Provide ceramic or tile resting surfaces.",
                "why": "Long coat combined with brachycephalic facial structure makes Persian cats particularly vulnerable to indoor heat accumulation.",
            })

    # ─── Sphynx ──────────────────────────────────────────────────────────────
    if breed_name == "Sphynx" and uv >= 5 and is_day:
        recs.append({
            "category": "Sun Exposure",
            "icon": "🌞",
            "advice": "Avoid direct sun patches and window basking during strong sunlight hours. "
                      "Hairless skin absorbs UV and heat rapidly — even short exposure to sun patches is risky.",
            "why": "Sphynx have high UV skin sensitivity despite lower coat insulation.",
        })

    # ─── Maine Coon / Golden / German Shepherd ───────────────────────────────
    if breed_name in ["Maine Coon", "Golden Retriever", "German Shepherd"] and heat_stress >= 50:
        recs.append({
            "category": "Environment",
            "icon": "🌬️",
            "advice": "Ensure strong airflow in the pet's primary resting zone. "
                      "Consider a fan directed at their resting area.",
            "why": "Large body mass with insulating coat increases heat retention and slows natural cooling.",
        })

    # ─── Senior modifier ─────────────────────────────────────────────────────
    if age_group == "senior" and overall_risk >= 30:
        recs.append({
            "category": "Age Consideration",
            "icon": "👴",
            "advice": "Senior pets have reduced heat tolerance. Apply the most conservative limits and "
                      "monitor more frequently than with younger animals.",
            "why": "Aging reduces cardiovascular and thermoregulatory efficiency, elevating heat risk.",
        })

    # ─── Overweight modifier ─────────────────────────────────────────────────
    if overweight and overall_risk >= 25:
        recs.append({
            "category": "Weight Risk",
            "icon": "⚖️",
            "advice": "Excess body weight significantly reduces heat tolerance. Limit activity duration "
                      "further than the base recommendation and monitor breathing closely.",
            "why": "Adipose tissue insulates and retains heat, reducing the body's ability to thermoregulate.",
        })

    # ─── Low-risk reassurance ────────────────────────────────────────────────
    if overall_risk < 25 and len(recs) == 0:
        recs.append({
            "category": "Routine Guidance",
            "icon": "✅",
            "advice": "Conditions are generally comfortable for routine activity. Keep water available and use normal observation during walks or play.",
            "why": "Current weather is within a manageable range for this breed with no major heat-related triggers detected.",
        })

    return recs


def generate_emergency_signs(breed: dict) -> dict:
    return {
        "signs": breed.get("key_warning_signs", []),
        "safe_note": (
            "⚠️ Stop activity immediately if you observe any of these signs. "
            "Move your pet to a cool, shaded environment and offer water. "
            "Consider urgent veterinary attention if symptoms escalate or do not improve promptly."
        ),
        "disclaimer": (
            "This app does not provide veterinary diagnosis. "
            "These are observational watch points only."
        ),
    }