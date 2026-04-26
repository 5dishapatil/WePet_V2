"""
community_app/views.py — Community mode views for WePet Django.

FINAL FLOW:
- Daily task logic preserved
- Community users can submit distress reports
- Community users can view their submitted alerts + NGO status
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.services.weather_service import get_weather_for_location
from core.services.risk_engine import compute_community_heat_score
from core.services.citizen_task_engine import select_task, get_best_task_time
from core.services.distress_service import submit_distress_report, get_reports_for_user
from community_app.models import TaskCompletion


# Simple symptom choices for community distress form
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

    completion_dates = set(
        c.completed_at.astimezone(timezone.get_current_timezone()).date()
        for c in completions
    )

    today = timezone.localdate()
    streak = 0
    current_day = today

    while current_day in completion_dates:
        streak += 1
        current_day = current_day - timedelta(days=1)

    return streak


@login_required(login_url="/accounts/login/")
def community_view(request):
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
    }
    return render(request, "community_app/community.html", context)


@login_required(login_url="/accounts/login/")
@require_POST
def fetch_task_view(request):
    location = request.POST.get("location", "").strip()

    if not location:
        request.session["comm_error"] = "Please enter your city to continue."
        return redirect("community:community")

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

    request.session["comm_data"] = {
        "current": current,
        "location_display": weather_data["location"]["display"],
        "heat_level": heat_level,
        "heat_score": heat_score,
        "task": task,
        "best_time": best_time,
        "location_raw": location,
        "completed": False,
    }

    return redirect("community:community")


@login_required(login_url="/accounts/login/")
@require_POST
def complete_task_view(request):
    comm_data = request.session.get("comm_data")

    if not comm_data or comm_data.get("completed"):
        return redirect("community:community")

    task = comm_data.get("task", {})
    task_id = task.get("id", "default")
    today = timezone.localdate()

    already_completed_today = TaskCompletion.objects.filter(
        user=request.user,
        task_id=task_id,
        completed_at__date=today,
    ).exists()

    if not already_completed_today:
        TaskCompletion.objects.create(
            user=request.user,
            task_id=task_id,
            task_text=task.get("task", ""),
            points=task.get("points", 10),
            location=comm_data.get("location_raw", ""),
        )

    comm_data["completed"] = True
    request.session["comm_data"] = comm_data

    return redirect("community:community")


@login_required(login_url="/accounts/login/")
@require_POST
def submit_distress_view(request):
    """
    Community user submits a distress ticket.
    """
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