"""
pets/views.py — Pet Owner page views for WePet Django.
Preserves ALL core logic from screens/pet_owner.py exactly,
with safe Django routing + JSON-safe breed detection.

FINAL FIXES INCLUDED:
- Save Pet now works after successful auto-detection
- If species is "Don't know" but breed is valid, species is auto-inferred from breed profile
- Analyze flow also auto-corrects species safely
- Detect endpoint ALWAYS returns JSON (never HTML)
- Session state preserved cleanly
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from pets.models import Pet, RiskHistory
from core.services.breed_profile_service import (
    get_dog_breeds,
    get_cat_breeds,
    get_breed_profile,
)
from core.services.weather_service import (
    get_weather_for_location,
    get_weather_for_coordinates,
    apply_location_display,
)
from core.services.location_service import reverse_geocode_osm
from core.services.risk_engine import (
    compute_pressures,
    compute_modifier_bonus,
    compute_heat_stress,
    compute_dehydration,
    compute_respiratory,
    compute_surface_burn,
    compute_indoor_heat,
    compute_overall_risk,
    risk_level_label,
    compute_hidden_risk_drivers,
    compute_safe_windows,
    compute_max_exposure,
)
from core.services.recommendation_engine import (
    generate_recommendations,
    generate_emergency_signs,
)
from core.services.breed_classifier_service import predict_from_bytes


# ──────────────────────────────────────────────────────────────────────────────
# Helper: infer species from breed profile if frontend still sends "Don't know"
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_species_and_breed(species: str, breed_name: str):
    """
    Returns:
        (resolved_species, breed_profile)

    Rules:
    - breed_name must be valid
    - if species is invalid/"Don't know", infer from breed profile
    - if species is valid but conflicts with profile, profile wins
    """
    if not breed_name:
        raise ValueError("Please select a breed or upload a photo for auto-detection.")

    breed = get_breed_profile(breed_name)
    if not breed:
        raise ValueError(
            "This breed is not yet supported in the climate-risk profile system. "
            "Please choose a supported breed."
        )

    profile_species = breed.get("species_type", "").strip()

    if species not in ["Dog", "Cat"]:
        if profile_species in ["Dog", "Cat"]:
            species = profile_species
        else:
            raise ValueError("Please select a valid species before continuing.")
    else:
        # If frontend species differs from actual profile species, trust profile
        if profile_species in ["Dog", "Cat"] and profile_species != species:
            species = profile_species

    return species, breed


# ──────────────────────────────────────────────────────────────────────────────
# Main page
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
def pet_owner_view(request):
    """
    Main pet owner page — GET shows form + any stored results.
    """
    user = request.user
    pets = list(Pet.objects.filter(user=user).order_by("-created_at"))
    dog_breeds = get_dog_breeds()
    cat_breeds = get_cat_breeds()

    results = request.session.get("pet_results")
    form_state = request.session.pop("form_state", {})
    error = request.session.pop("pet_error", None)
    success_msg = request.session.pop("pet_success", None)

    context = {
        "pets": pets,
        "dog_breeds": dog_breeds,
        "cat_breeds": cat_breeds,
        "results": results,
        "form_state": form_state,
        "error": error,
        "success_msg": success_msg,
    }
    return render(request, "pets/pet_owner.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# Analyze risk
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
@require_POST
def analyze_view(request):
    """
    Run risk analysis — POST, stores results in session, redirects to GET.
    """
    user = request.user

    # ── Collect form data ──────────────────────────────────────────────────
    pet_name = request.POST.get("pet_name", "").strip()
    species = request.POST.get("species", "Dog").strip()
    breed_name = request.POST.get("breed_name", "").strip()
    age_group = request.POST.get("age_group", "Adult").strip()
    overweight = request.POST.get("overweight") == "on"
    heat_sensitive = request.POST.get("heat_sensitive") == "on"

    location_mode = request.POST.get("location_mode", "manual").strip()
    location_text = request.POST.get("location_text", "").strip()
    lat_str = request.POST.get("geo_lat", "").strip()
    lon_str = request.POST.get("geo_lon", "").strip()
    selected_pet_id = request.POST.get("selected_pet_id", "").strip()
    location_label_override = request.POST.get("location_label", "").strip()

    # Preserve form state for re-display
    form_state = {
        "pet_name": pet_name,
        "species": species,
        "breed_name": breed_name,
        "age_group": age_group,
        "overweight": overweight,
        "heat_sensitive": heat_sensitive,
        "location_mode": location_mode,
        "location_text": location_text,
        "selected_pet_id": selected_pet_id,
    }

    # ── Validate / resolve breed + species ─────────────────────────────────
    try:
        species, breed = _resolve_species_and_breed(species, breed_name)
        form_state["species"] = species  # important: keep UI consistent after redirect
    except ValueError as exc:
        request.session["pet_error"] = str(exc)
        request.session["form_state"] = form_state
        return redirect("pets:pet_owner")

    # ── Fetch weather ──────────────────────────────────────────────────────
    if location_mode == "gps" and lat_str and lon_str:
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            request.session["pet_error"] = "Invalid GPS coordinates received."
            request.session["form_state"] = form_state
            return redirect("pets:pet_owner")

        weather_data = get_weather_for_coordinates(lat, lon)

        if "error" not in weather_data:
            if location_label_override:
                label = location_label_override
            else:
                geo = reverse_geocode_osm(lat, lon)
                label = geo.get("display", f"{lat:.4f}, {lon:.4f}")

            weather_data = apply_location_display(weather_data, label)

    else:
        if not location_text:
            request.session["pet_error"] = "Please enter your city or allow location access."
            request.session["form_state"] = form_state
            return redirect("pets:pet_owner")

        weather_data = get_weather_for_location(location_text)

    if "error" in weather_data:
        request.session["pet_error"] = f"Could not fetch weather: {weather_data['error']}"
        request.session["form_state"] = form_state
        return redirect("pets:pet_owner")

    # ── Run risk engine ────────────────────────────────────────────────────
    current = weather_data["current"]
    hourly = weather_data.get("hourly", [])
    location_display = weather_data["location"]["display"]

    pressures = compute_pressures(current, breed)
    mod_bonus = compute_modifier_bonus(age_group.lower(), overweight, heat_sensitive)

    sub_scores = {
        "heat_stress": compute_heat_stress(pressures, breed, mod_bonus),
        "dehydration": compute_dehydration(pressures, breed, mod_bonus),
        "respiratory": compute_respiratory(pressures, breed, mod_bonus),
        "surface_burn": compute_surface_burn(pressures, breed, current),
        "indoor_heat": compute_indoor_heat(pressures, breed),
    }

    overall_risk = compute_overall_risk(sub_scores)
    risk_level = risk_level_label(overall_risk)
    drivers = compute_hidden_risk_drivers(current, breed, sub_scores)
    windows = compute_safe_windows(hourly, breed)
    exposure = compute_max_exposure(
        risk_level,
        breed,
        sub_scores,
        age_group.lower(),
        overweight,
        heat_sensitive,
    )

    recs = generate_recommendations(
        breed=breed,
        weather=current,
        sub_scores=sub_scores,
        overall_risk=overall_risk,
        risk_level=risk_level,
        age_group=age_group.lower(),
        overweight=overweight,
        heat_sensitive=heat_sensitive,
    )

    emergency = generate_emergency_signs(breed)

    # ── Store results in session ───────────────────────────────────────────
    request.session["pet_results"] = {
        "current": current,
        "location_display": location_display,
        "sub_scores": sub_scores,
        "overall_risk": overall_risk,
        "risk_level": risk_level,
        "drivers": drivers,
        "windows": windows,
        "exposure": exposure,
        "recs": recs,
        "emergency": emergency,
        "species": species.lower(),   # keep template compatibility for {% if results.species == 'dog' %}
        "breed_name": breed_name,
        "pet_name": pet_name,
    }

    # ── Save risk history for existing saved pet ───────────────────────────
    if selected_pet_id:
        try:
            saved_pet = Pet.objects.get(pk=int(selected_pet_id), user=user)
            RiskHistory.objects.create(
                user=user,
                pet=saved_pet,
                location=location_display,
                temperature=float(current.get("temperature", 0.0)),
                apparent_temperature=float(current.get("apparent_temperature", 0.0)),
                humidity=int(current.get("humidity", 0)),
                risk_score=float(overall_risk),
                risk_level=risk_level,
            )
        except (Pet.DoesNotExist, ValueError, TypeError):
            pass

    request.session["form_state"] = form_state
    return redirect("pets:pet_owner")


# ──────────────────────────────────────────────────────────────────────────────
# Save pet profile
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
@require_POST
def save_pet_view(request):
    """
    Save a pet profile to the database.

    FINAL FIX:
    If species is "Don't know" but breed is valid (auto-detected),
    species is inferred from the breed profile and save proceeds.
    """
    user = request.user

    pet_name = request.POST.get("pet_name", "").strip()
    species = request.POST.get("species", "").strip()
    breed_name = request.POST.get("breed_name", "").strip()
    age_group = request.POST.get("age_group", "Adult").strip()
    overweight = request.POST.get("overweight") == "on"
    heat_sensitive = request.POST.get("heat_sensitive") == "on"

    form_state = {
        "pet_name": pet_name,
        "species": species,
        "breed_name": breed_name,
        "age_group": age_group,
        "overweight": overweight,
        "heat_sensitive": heat_sensitive,
        "location_mode": request.POST.get("location_mode", "manual"),
        "location_text": request.POST.get("location_text", ""),
        "selected_pet_id": request.POST.get("selected_pet_id", ""),
    }

    if not pet_name:
        request.session["pet_error"] = "Please enter a pet name before saving."
        request.session["form_state"] = form_state
        return redirect("pets:pet_owner")

    # Resolve species safely from breed if needed
    try:
        species, breed = _resolve_species_and_breed(species, breed_name)
        form_state["species"] = species
    except ValueError as exc:
        request.session["pet_error"] = str(exc)
        request.session["form_state"] = form_state
        return redirect("pets:pet_owner")

    # Prevent duplicate same-name pets for same user (optional but helpful)
    existing = Pet.objects.filter(
        user=user,
        pet_name__iexact=pet_name,
        breed__iexact=breed_name,
    ).first()

    if existing:
        request.session["pet_success"] = f"{pet_name} is already saved."
        request.session["form_state"] = form_state
        return redirect("pets:pet_owner")

    Pet.objects.create(
        user=user,
        pet_name=pet_name,
        species=species,
        breed=breed_name,
        age_group=age_group,
        overweight=overweight,
        heat_sensitive=heat_sensitive,
    )

    request.session["pet_success"] = f"Saved pet profile for {pet_name}!"
    request.session["form_state"] = form_state
    return redirect("pets:pet_owner")


# ──────────────────────────────────────────────────────────────────────────────
# Delete saved pet
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
@require_POST
def delete_pet_view(request, pet_id):
    """
    Delete a saved pet.
    """
    pet = get_object_or_404(Pet, pk=pet_id, user=request.user)
    pet.delete()
    request.session["pet_success"] = "Pet profile deleted."
    return redirect("pets:pet_owner")


# ──────────────────────────────────────────────────────────────────────────────
# AJAX breed detection
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
@require_POST
def detect_breed_view(request):
    """
    AJAX endpoint:
    Accept uploaded image bytes, run breed classifier,
    return JSON only.

    IMPORTANT:
    This MUST always return JSON — never HTML —
    otherwise frontend JS crashes with:
    Unexpected token '<'
    """
    try:
        if "pet_image" not in request.FILES:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "No image uploaded."
                },
                status=400,
            )

        image_file = request.FILES["pet_image"]
        image_bytes = image_file.read()

        if not image_bytes:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Uploaded image is empty."
                },
                status=400,
            )

        result = predict_from_bytes(image_bytes)

        if not isinstance(result, dict):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Classifier returned invalid response."
                },
                status=500,
            )

        # Always JSON only
        return JsonResponse(result)

    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": f"Detection failed: {str(exc)}"
            },
            status=500,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Clear session results
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
def clear_results_view(request):
    """
    Clear stored risk results from session.
    """
    request.session.pop("pet_results", None)
    return redirect("pets:pet_owner")