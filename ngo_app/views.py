from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from ngo_app.models import ShelterProfile, AnimalGroup
from ngo_app.forms import ShelterProfileForm, AnimalGroupForm

from core.services.weather_service import get_weather_for_location, get_weather_for_coordinates
from core.services.breed_profile_service import get_breed_profile, get_dog_breeds, get_cat_breeds
from core.services.risk_engine import compute_community_heat_score, compute_ngo_group_risk
from core.services.distress_service import get_all_reports_sorted, update_report_status
from core.services.breed_classifier_service import predict_from_bytes
import json


def _get_or_create_shelter(user):
    shelter, _ = ShelterProfile.objects.get_or_create(
        user=user,
        defaults={
            "shelter_name": f"{user.username}'s Shelter",
        }
    )
    return shelter


@login_required(login_url="/accounts/login/")
def ngo_view(request):
    shelter = _get_or_create_shelter(request.user)

    shelter_form = ShelterProfileForm(instance=shelter)
    group_form = AnimalGroupForm()

    groups = AnimalGroup.objects.filter(shelter=shelter)

    weather_data = None
    weather_error = None
    climate_summary = None
    monitor_rows = []

    # Fetch weather ONCE for the entire shelter if location exists
    if shelter.location_label:
        try:
            if shelter.geo_lat and shelter.geo_lon:
                weather_data = get_weather_for_coordinates(shelter.geo_lat, shelter.geo_lon)
                if weather_data and "error" not in weather_data:
                    weather_data["location"]["display"] = shelter.location_label
            else:
                weather_data = get_weather_for_location(shelter.location_label)
        except Exception as e:
            weather_data = {"error": f"Weather lookup failed: {str(e)}"}

        if not weather_data or "error" in weather_data:
            weather_error = (weather_data or {}).get(
                "error",
                "Could not fetch weather for this shelter location."
            )
        else:
            current = weather_data["current"]

            try:
                climate_summary = compute_community_heat_score(current)
            except Exception as e:
                weather_error = f"Climate scoring failed: {str(e)}"
                climate_summary = None

            if climate_summary is not None:
                for group in groups:
                    try:
                        breed_profile = get_breed_profile(group.breed_name)
                        group_risk = compute_ngo_group_risk(current, breed_profile)

                        row = {
                            "group": group,
                            "risk_score": group_risk.get("risk_score", 0),
                            "risk_level": group_risk.get("risk_level", "Low"),
                            "recommendations": group_risk.get("recommendations", []),
                            "watch_signs": group_risk.get("watch_signs", []),
                            "reason": group_risk.get("reason", ""),
                        }
                        monitor_rows.append(row)

                    except Exception as e:
                        row = {
                            "group": group,
                            "risk_score": 0,
                            "risk_level": "Low",
                            "recommendations": ["Profile unavailable — please verify breed support."],
                            "watch_signs": [],
                            "reason": str(e),
                        }
                        monitor_rows.append(row)

                level_rank = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1}
                monitor_rows.sort(
                    key=lambda x: (
                        level_rank.get(x["risk_level"], 0),
                        x["risk_score"],
                        x["group"].count,
                    ),
                    reverse=True
                )

    # Distress tickets
    try:
        reports = get_all_reports_sorted()
    except Exception:
        reports = []

    level_counts = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
    status_counts = {
        "No Response": 0,
        "Acknowledged": 0,
        "On Hold": 0,
        "Action Taken": 0,
    }

    for r in reports:
        lvl = r.get("severity_level", "Low")
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

        status = r.get("status", "No Response")
        status_counts[status] = status_counts.get(status, 0) + 1

    total_groups = groups.count()
    total_animals = sum(g.count for g in groups)
    critical_groups = sum(1 for r in monitor_rows if r["risk_level"] == "Critical")
    high_groups = sum(1 for r in monitor_rows if r["risk_level"] == "High")
    pending_reports = (
        status_counts["No Response"] +
        status_counts["Acknowledged"] +
        status_counts["On Hold"]
    )

    error = request.session.pop("ngo_error", None)
    success = request.session.pop("ngo_success", None)

    active_tab = request.GET.get("tab", "dashboard")

    context = {
        "shelter": shelter,
        "shelter_form": shelter_form,
        "group_form": group_form,
        "groups": groups,

        "weather_data": weather_data if weather_data and "error" not in weather_data else None,
        "weather_error": weather_error,
        "climate_summary": climate_summary,
        "monitor_rows": monitor_rows,

        "reports": reports,
        "level_counts": level_counts,
        "status_counts": status_counts,

        "total_groups": total_groups,
        "total_animals": total_animals,
        "critical_groups": critical_groups,
        "high_groups": high_groups,
        "pending_reports": pending_reports,

        "error": error,
        "success": success,
        "active_tab": active_tab,

        # For JS fallback dropdown logic
        "dog_breeds_js": get_dog_breeds(),
        "cat_breeds_js": get_cat_breeds(),
    }

    return render(request, "ngo_app/ngo.html", context)


@login_required(login_url="/accounts/login/")
@require_POST
def save_shelter_location_view(request):
    shelter = _get_or_create_shelter(request.user)

    shelter_name = request.POST.get("shelter_name", "").strip()
    location_label = request.POST.get("location_label", "").strip()
    geo_lat = request.POST.get("geo_lat", "").strip()
    geo_lon = request.POST.get("geo_lon", "").strip()

    if not shelter_name:
        request.session["ngo_error"] = "Please enter a shelter name."
        return redirect("/ngo/?tab=registry")

    if not location_label:
        request.session["ngo_error"] = "Please set a shelter location to enable live climate monitoring."
        return redirect("/ngo/?tab=registry")

    shelter.shelter_name = shelter_name
    shelter.location_label = location_label
    shelter.geo_lat = geo_lat
    shelter.geo_lon = geo_lon
    shelter.location_locked = bool(location_label)
    shelter.save()

    request.session["ngo_success"] = "Shelter profile and location saved successfully."
    return redirect("/ngo/?tab=registry")


@login_required(login_url="/accounts/login/")
@require_POST
def add_group_view(request):
    shelter = _get_or_create_shelter(request.user)

    form = AnimalGroupForm(request.POST)

    if not form.is_valid():
        # Surface form errors cleanly
        first_error = None
        for field, errs in form.errors.items():
            if errs:
                first_error = errs[0]
                break

        request.session["ngo_error"] = first_error or "Please enter a valid species, breed, and count."
        return redirect("/ngo/?tab=registry")

    group = form.save(commit=False)
    group.shelter = shelter

    # Final hard safety: if detected values were used, they are already in cleaned_data,
    # but we enforce explicitly to avoid hidden-field mismatch bugs.
    detected_species = form.cleaned_data.get("detected_species", "").strip()
    detected_breed = form.cleaned_data.get("detected_breed", "").strip()

    if detected_breed:
        group.breed_name = detected_breed
    if detected_species in ["Dog", "Cat"]:
        group.species = detected_species

    # Validate supported profile exists
    if not get_breed_profile(group.breed_name):
        request.session["ngo_error"] = (
            "This breed is recognised but not yet supported by the climate-risk profile system. "
            "Please choose the closest supported breed manually."
        )
        return redirect("/ngo/?tab=registry")

    group.save()

    request.session["ngo_success"] = f"Added {group.breed_name} × {group.count} to registry."
    return redirect("/ngo/?tab=registry")


@login_required(login_url="/accounts/login/")
@require_POST
def delete_group_view(request, group_id):
    shelter = _get_or_create_shelter(request.user)
    group = get_object_or_404(AnimalGroup, id=group_id, shelter=shelter)

    label = f"{group.breed_name} × {group.count}"
    group.delete()

    request.session["ngo_success"] = f"Removed {label} from registry."
    return redirect("/ngo/?tab=registry")


@login_required(login_url="/accounts/login/")
@require_POST
def update_report_view(request, report_id):
    """
    NGO updates community-submitted distress ticket status.
    """
    status = request.POST.get("status", "").strip()
    ngo_note = request.POST.get("ngo_note", "").strip()
    proof_location = request.POST.get("proof_location", "").strip()

    proof_photo = request.FILES.get("proof_photo")
    proof_image_name = proof_photo.name if proof_photo else None

    if status == "Action Taken":
        if not proof_image_name:
            request.session["ngo_error"] = "To mark Action Taken, you must upload a proof photo."
            return redirect("/ngo/?tab=tickets")
        if not proof_location:
            request.session["ngo_error"] = "To mark Action Taken, you must enter the proof location."
            return redirect("/ngo/?tab=tickets")

    ok = update_report_status(
        report_id=report_id,
        status=status,
        ngo_username=request.user.username,
        ngo_note=ngo_note,
        proof_image_name=proof_image_name,
        proof_location=proof_location,
    )

    if ok:
        request.session["ngo_success"] = f"Ticket {report_id} updated successfully."
    else:
        request.session["ngo_error"] = f"Could not update ticket {report_id}. Please check the inputs."

    return redirect("/ngo/?tab=tickets")


# ──────────────────────────────────────────────────────────────────────────────
# NGO AJAX breed detection
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url="/accounts/login/")
@require_POST
def ngo_detect_breed_view(request):
    """
    NGO-specific AJAX endpoint for breed detection.
    Returns JSON only.
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

        return JsonResponse(result)

    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": f"Detection failed: {str(exc)}"
            },
            status=500,
        )