"""
core/services/citizen_task_engine.py — Task selection logic for Community User mode.
Migrated from services/citizen_task_engine.py — logic unchanged, path updated for Django.
"""
import json
import random
from datetime import datetime
from pathlib import Path
from django.conf import settings


def _get_tasks_file() -> Path:
    return settings.DATA_DIR / "citizen_tasks.json"


def _load_tasks() -> dict:
    try:
        with open(_get_tasks_file(), "r") as f:
            return json.load(f)
    except Exception:
        return {"tasks": {}}


def select_task(heat_level: str) -> dict:
    """Select today's community task based on heat severity level."""
    data = _load_tasks()
    tasks_by_level = data.get("tasks", {})

    if heat_level in ("High", "Critical"):
        pool = tasks_by_level.get("high_critical", [])
    elif heat_level == "Moderate":
        pool = tasks_by_level.get("moderate", [])
    else:
        pool = tasks_by_level.get("low", [])

    if not pool:
        return {
            "id": "default",
            "task": "Refill an outdoor water source for street animals",
            "why": "Animals always benefit from accessible clean water.",
            "effort": "1 minute",
            "points": 10,
        }

    seed = int(datetime.now().strftime("%Y%m%d"))
    random.seed(seed)
    return random.choice(pool)


def get_best_task_time(current_hour: int) -> str:
    """Return recommendation for best time to complete the task."""
    if current_hour < 10:
        return "✅ Now is a great time — complete before 10 AM if possible."
    elif 10 <= current_hour < 17:
        return "🌅 Late evening would be better, but if it's urgent (like water refill), do it now."
    else:
        return "🌇 Now is a good time — refill or reset shaded water sources for the night."