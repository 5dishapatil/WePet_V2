"""
community_app/views.py — Community mode views for WePet Django.

FINAL FLOW:
- Daily task logic preserved
- Community users can submit distress reports
- Community users can view their submitted alerts + NGO status
- Community users can access Rewards page and claim simulated vouchers
"""

from datetime import timedelta
import random
import string

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.services.weather_service import get_weather_for_location
from core.services.risk_engine import compute_community_heat_score
from core.services.citizen_task_engine import select_task, get_best_task_time
from core.services.distress_service import submit_distress_report, get_reports_for_user

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

    # Prevent duplicate completion of same task_id on same day
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
        request.session["comm_success"] = (
            f"Task completed! You earned +{task.get('points', 10)} points 🎉"
        )
    else:
        request.session["comm_success"] = (
            "You have already completed this task today."
        )

    comm_data["completed"] = True
    request.session["comm_data"] = comm_data

    return redirect("community:community")


# ──────────────────────────────────────────────────────────────────────────────
# Distress Submission (Community → NGO)
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# Rewards Page
# ──────────────────────────────────────────────────────────────────────────────

@login_required(login_url="/accounts/login/")
def rewards_view(request):
    """
    Rewards page:
    - show total points
    - show streak
    - show unlock progress
    - show claimed simulated vouchers
    """
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
    }
    return render(request, "community_app/community.html", context)


@login_required(login_url="/accounts/login/")
@require_POST
def claim_reward_view(request, milestone):
    """
    Claim a simulated reward if the user is eligible and hasn't claimed it yet.
    """
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
