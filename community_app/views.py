"""
community_app/views.py — Community mode views for WePet Django.
"""

import math
from datetime import timedelta
import random
import string
import io
import requests
from PIL import Image, ExifTags

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.services.weather_service import get_weather_for_location
from core.services.risk_engine import compute_community_heat_score
from core.services.citizen_task_engine import select_task, get_best_task_time
from core.services.distress_service import submit_distress_report, get_reports_for_user
from core.services.osm_service import fetch_nearby_shelters, _geocode_city
from community_app.models import TaskCompletion, RewardClaim

# ──────────────────────────────────────────────────────────────────────────────
# Community Distress Form Options
# ──────────────────────────────────────────────────────────────────────────────

DISTRESS_SYMPTOMS = [
    "Panting heavily",
    "Weak / unable to stand",
    "Lethargic / collapsed",
    "Vomiting",
    "Seizure / trembling",
    "Injured / bleeding",
    "Limping",
    "Disoriented",
    "Dehydrated / dry gums",
    "Unresponsive",
]


# ──────────────────────────────────────────────────────────────────────────────
# Simulated Reward Tiers
# ──────────────────────────────────────────────────────────────────────────────

REWARD_TIERS = [
    {
        "milestone": 100,
        "amount": 50,
        "reward_name": "Amazon Cash Voucher ₹50 (Simulated)",
    },
    {
        "milestone": 250,
        "amount": 150,
        "reward_name": "Amazon Cash Voucher ₹150 (Simulated)",
    },
    {
        "milestone": 500,
        "amount": 400,
        "reward_name": "Amazon Cash Voucher ₹400 (Simulated)",
    },
    {
        "milestone": 1000,
        "amount": 1000,
        "reward_name": "Amazon Cash Voucher ₹1000 (Simulated)",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_user_total_points(user):
    total = (
        TaskCompletion.objects.filter(user=user)
        .aggregate(total_points=Sum("points"))
        .get("total_points")
    )
    return total or 0


def get_user_streak_days(user):
    completions = TaskCompletion.objects.filter(user=user).order_by("-completed_at")
    if not completions.exists():
        return 0

    # FIX 2: Use timezone.localtime() instead of astimezone() to prevent 500 errors 
    # if the server returns a naive datetime object.
    completion_dates = set(
        timezone.localtime(c.completed_at).date()
        for c in completions
    )

    today = timezone.localdate()
    streak = 0
    current_day = today

    while current_day in completion_dates:
        streak += 1
        current_day = current_day - timedelta(days=1)

    return streak


def generate_fake_voucher_code(amount: int) -> str:
    """
    Generates a fake Amazon-style voucher code for demo purposes.
    Example: AMZ-50-8KQX9P2M
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"AMZ-{amount}-{suffix}"


def build_reward_rows(user):
    """
    Build reward UI rows:
    - eligible
    - claimed
    - progress percentage
    - remaining points
    """
    total_points = get_user_total_points(user)

    claimed_map = {
        claim.milestone_points: claim
        for claim in RewardClaim.objects.filter(user=user)
    }

    reward_rows = []
    for tier in REWARD_TIERS:
        milestone = tier["milestone"]
        claim_obj = claimed_map.get(milestone)

        progress_pct = 0
        if milestone > 0:
            progress_pct = min(int((total_points / milestone) * 100), 100)

        reward_rows.append({
            "milestone": milestone,
            "amount": tier["amount"],
            "reward_name": tier["reward_name"],
            "eligible": total_points >= milestone,
            "claimed": claim_obj is not None,
            "claim": claim_obj,
            "progress_pct": progress_pct,
            "remaining_points": max(milestone - total_points, 0),
        })

    return reward_rows


# ──────────────────────────────────────────────────────────────────────────────
# Main Community Page
# ──────────────────────────────────────────────────────────────────────────────

@login_required(login_url="/accounts/login/")
def community_view(request):
    """
    Main community page:
    - climate task flow
    - points + streak
    - distress submission
    - user's submitted distress reports
    """
    comm_data = request.session.get("comm_data")
    total_pts = get_user_total_points(request.user)
    streak = get_user_streak_days(request.user)

    error = request.session.pop("comm_error", None)
    success = request.session.pop("comm_success", None)

    my_reports = []
    try:
        my_reports = get_reports_for_user(request.user.username)
    except Exception:
        my_reports = []

    context = {
        "comm_data": comm_data,
        "total_pts": total_pts,
        "streak": streak,
        "error": error,
        "success": success,
        "my_reports": my_reports,
        "distress_symptoms": DISTRESS_SYMPTOMS,
        "active_tab": "community",
        "saved_city": request.session.get("saved_user_city", ""), 
    }
    return render(request, "community_app/community.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# Climate Task Flow
# ──────────────────────────────────────────────────────────────────────────────

@login_required(login_url="/accounts/login/")
@require_POST
def fetch_task_view(request):
    location = request.POST.get("location", "").strip()

    if not location:
        request.session["comm_error"] = "Please enter your city to continue."
        return redirect("community:community")

    request.session["saved_user_city"] = location

    city_coords = _geocode_city(location)
    city_lat, city_lon = city_coords if city_coords else (None, None)

    weather_data = get_weather_for_location(location)
    if "error" in weather_data:
        request.session["comm_error"] = f"Could not fetch weather: {weather_data['error']}"
        return redirect("community:community")

    current = weather_data["current"]
    heat_data = compute_community_heat_score(current)
    heat_level = heat_data["level"]
    heat_score = heat_data["score"]

    task = select_task(heat_level)
    current_hour = timezone.localtime().hour
    best_time = get_best_task_time(current_hour)

    shelters_data = fetch_nearby_shelters(location)

    request.session["comm_data"] = {
        "current": current,
        "location_display": weather_data["location"]["display"],
        "heat_level": heat_level,
        "heat_score": heat_score,
        "task": task,
        "best_time": best_time,
        "location_raw": location,
        "city_lat": city_lat, 
        "city_lon": city_lon, 
        "completed": False,
        "shelters": shelters_data,
    }

    return redirect("community:community")


def _extract_gps_from_image(image_file):
    """Bulletproof EXIF reader that handles Apple/Android fraction formats."""
    try:
        image_file.seek(0)
        img = Image.open(image_file)
        exif_data = img._getexif()
        
        if not exif_data:
            return None

        gps_info = None
        for tag, value in exif_data.items():
            if ExifTags.TAGS.get(tag, tag) == "GPSInfo":
                gps_info = value
                break

        if not gps_info:
            return None

        lat_ref = gps_info.get(1)
        lat = gps_info.get(2)
        lon_ref = gps_info.get(3)
        lon = gps_info.get(4)

        if not all([lat_ref, lat, lon_ref, lon]):
            return None

        def to_float(val):
            if isinstance(val, tuple):
                return float(val[0]) / float(val[1]) if val[1] != 0 else 0.0
            return float(val)

        def to_decimal(dms, ref):
            deg, min, sec = to_float(dms[0]), to_float(dms[1]) / 60.0, to_float(dms[2]) / 3600.0
            val = round(deg + min + sec, 5)
            return -val if ref in ['S', 'W'] else val

        final_lat = to_decimal(lat, lat_ref)
        final_lon = to_decimal(lon, lon_ref)
        
        return final_lat, final_lon
        
    except Exception as e:
        print(f"DEBUG: Image parsing crashed -> {str(e)}")
        return None


def _calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates distance in kilometers between two GPS points using the Haversine formula."""
    try:
        # FIX 1: Safely cast to float. Session data often serializes numeric values to strings. 
        # Without this, math.radians() will crash the server if fed a string.
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        
        R = 6371.0 
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2)**2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except (TypeError, ValueError):
        # Fallback to prevent crash if data is totally corrupted
        return 9999.0 


@login_required(login_url="/accounts/login/")
@require_POST
def complete_task_view(request):
    comm_data = request.session.get("comm_data")

    if not comm_data or comm_data.get("completed"):
        return redirect("community:community")

    proof_photo = request.FILES.get("proof_photo")
    if not proof_photo:
        request.session["comm_error"] = "Please upload a photo as proof of your action."
        return redirect("community:community")

    coords = _extract_gps_from_image(proof_photo)
    if not coords:
        request.session["comm_error"] = "❌ No GPS Geotag found in the photo. Please ensure Location is enabled in your camera settings."
        return redirect("community:community")

    photo_lat, photo_lon = coords
    city_lat = comm_data.get("city_lat")
    city_lon = comm_data.get("city_lon")
    expected_location = comm_data.get("location_raw", "")
    
    # Safely evaluate distance now that the math function is heavily armored
    if city_lat is not None and city_lon is not None:
        distance = _calculate_distance(city_lat, city_lon, photo_lat, photo_lon)
        if distance > 50.0: 
            request.session["comm_error"] = f"❌ Location mismatch! The photo was taken {int(distance)}km away from {expected_location}."
            return redirect("community:community")

    task = comm_data.get("task", {})
    task_id = task.get("id", "default")
    points_to_award = int(task.get("points", 10)) 

    already_completed_today = False 

    if not already_completed_today:
        TaskCompletion.objects.create(
            user=request.user,
            task_id=task_id,
            task_text=task.get("task", ""),
            points=points_to_award,
            location=expected_location,
        )
        request.session["comm_success"] = f"Photo verified! You earned +{points_to_award} points 🎉"
    else:
        request.session["comm_success"] = "You have already completed this task today."

    comm_data["completed"] = True
    request.session["comm_data"] = comm_data

    return redirect("community:community")


# ──────────────────────────────────────────────────────────────────────────────
# Distress Submission (Community → NGO)
# ──────────────────────────────────────────────────────────────────────────────

@login_required(login_url="/accounts/login/")
@require_POST
def submit_distress_view(request):
    location = request.POST.get("distress_location", "").strip()
    animal_type = request.POST.get("animal_type", "").strip()
    weather_level = request.POST.get("heat_level", "moderate").strip()
    notes = request.POST.get("notes", "").strip()
    symptoms = request.POST.getlist("symptoms")

    geo_lat = request.POST.get("geo_lat", "").strip()
    geo_lon = request.POST.get("geo_lon", "").strip()
    event_time = request.POST.get("event_time", "").strip()

    photo = request.FILES.get("photo")

    if not location:
        request.session["comm_error"] = "Please enter the location where the animal was spotted."
        return redirect("community:community")

    if animal_type.lower() not in {"dog", "cat", "other"}:
        request.session["comm_error"] = "Please choose a valid animal type."
        return redirect("community:community")

    image_name = photo.name if photo else None

    try:
        report = submit_distress_report(
            reporter_username=request.user.username,
            reporter_display_name=request.user.get_full_name() or request.user.username,
            location=location,
            animal_type=animal_type,
            symptoms=symptoms,
            notes=notes,
            weather_level=weather_level,
            image_name=image_name,
            geo_lat=geo_lat,
            geo_lon=geo_lon,
            event_time=event_time,
        )
        request.session["comm_success"] = (
            f"Distress alert submitted successfully. Ticket ID: {report['report_id']}"
        )
    except Exception as exc:
        request.session["comm_error"] = f"Could not submit distress alert: {str(exc)}"

    return redirect("community:community")


# ──────────────────────────────────────────────────────────────────────────────
# Rewards Page
# ──────────────────────────────────────────────────────────────────────────────

@login_required(login_url="/accounts/login/")
def rewards_view(request):
    total_pts = get_user_total_points(request.user)
    streak = get_user_streak_days(request.user)

    error = request.session.pop("comm_error", None)
    success = request.session.pop("comm_success", None)

    reward_rows = build_reward_rows(request.user)

    context = {
        "total_pts": total_pts,
        "streak": streak,
        "reward_rows": reward_rows,
        "error": error,
        "success": success,
        "active_tab": "rewards",
        "saved_city": request.session.get("saved_user_city", ""),
    }
    return render(request, "community_app/community.html", context)


@login_required(login_url="/accounts/login/")
@require_POST
def claim_reward_view(request, milestone):
    total_pts = get_user_total_points(request.user)

    tier = next((t for t in REWARD_TIERS if t["milestone"] == milestone), None)
    if not tier:
        request.session["comm_error"] = "Invalid reward tier selected."
        return redirect("community:rewards")

    if total_pts < milestone:
        request.session["comm_error"] = (
            f"You need {milestone - total_pts} more points to unlock this reward."
        )
        return redirect("community:rewards")

    existing = RewardClaim.objects.filter(
        user=request.user,
        milestone_points=milestone,
    ).first()

    if existing:
        request.session["comm_success"] = "You have already claimed this reward."
        return redirect("community:rewards")

    claim = RewardClaim.objects.create(
        user=request.user,
        milestone_points=milestone,
        reward_name=tier["reward_name"],
        voucher_amount=tier["amount"],
        voucher_code=generate_fake_voucher_code(tier["amount"]),
        status="claimed",
    )

    request.session["comm_success"] = (
        f"Reward claimed successfully! Your simulated voucher code: {claim.voucher_code}"
    )

    return redirect("community:rewards")
