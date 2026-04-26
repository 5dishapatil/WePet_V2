"""
core/services/distress_service.py — Community distress ticket system for WePet MVP.

NEW FLOW:
- Community users submit distress alerts
- NGO users only view + update tickets
- Tickets persist in JSON for MVP compatibility
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from django.conf import settings

from core.services.storage_service import read_json, write_json


# ─────────────────────────────────────────────────────────────
# Internal file path
# ─────────────────────────────────────────────────────────────

def _get_distress_file() -> Path:
    return settings.DATA_DIR / "distress_reports.json"


def _default_payload() -> Dict[str, Any]:
    return {"reports": [], "next_id": 1001}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _normalize_symptoms(symptoms) -> List[str]:
    if isinstance(symptoms, str):
        s = symptoms.strip()
        return [s] if s else []
    if isinstance(symptoms, (list, tuple)):
        return [str(x).strip() for x in symptoms if str(x).strip()]
    return []


def _compute_severity(weather_level: str, symptoms_list: List[str]) -> Dict[str, Any]:
    weather_level = str(weather_level).strip().lower()

    base_score = {
        "low": 20,
        "moderate": 45,
        "high": 70,
        "critical": 90,
    }.get(weather_level, 45)

    severity_score = min(100, base_score + len(symptoms_list) * 8)

    if severity_score >= 85:
        severity_level = "Critical"
        urgency = "Immediate rescue response needed."
    elif severity_score >= 65:
        severity_level = "High"
        urgency = "High-priority field response recommended soon."
    elif severity_score >= 40:
        severity_level = "Moderate"
        urgency = "Monitor and respond if symptoms worsen."
    else:
        severity_level = "Low"
        urgency = "Low immediate danger, but keep observing."

    return {
        "severity_score": severity_score,
        "severity_level": severity_level,
        "urgency": urgency,
    }


# ─────────────────────────────────────────────────────────────
# Base persistence
# ─────────────────────────────────────────────────────────────

def load_distress_reports() -> List[Dict[str, Any]]:
    data = read_json(_get_distress_file(), _default_payload())
    return data.get("reports", [])


def save_distress_reports(reports: List[Dict[str, Any]], next_id: Optional[int] = None) -> bool:
    data = read_json(_get_distress_file(), _default_payload())
    payload = {
        "reports": reports,
        "next_id": next_id if next_id is not None else data.get("next_id", 1001),
    }
    return write_json(_get_distress_file(), payload)


# ─────────────────────────────────────────────────────────────
# Community submits ticket
# ─────────────────────────────────────────────────────────────

def submit_distress_report(
    reporter_username: str,
    reporter_display_name: str,
    location: str,
    animal_type: str,
    symptoms,
    notes: str = "",
    weather_level: str = "moderate",
    image_name: Optional[str] = None,
    geo_lat: Optional[str] = None,
    geo_lon: Optional[str] = None,
    event_time: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new community-submitted distress ticket.
    """

    data = read_json(_get_distress_file(), _default_payload())

    report_id = f"PT-{data.get('next_id', 1001)}"
    submitted_at = datetime.now().isoformat()

    symptoms_list = _normalize_symptoms(symptoms)
    sev = _compute_severity(weather_level, symptoms_list)

    report = {
        "report_id": report_id,
        "submitted_at": submitted_at,
        "updated_at": submitted_at,

        # reporter
        "reporter_username": str(reporter_username).strip(),
        "reporter_display_name": str(reporter_display_name).strip(),

        # core ticket
        "location": str(location).strip(),
        "animal_type": str(animal_type).strip().lower(),
        "symptoms": symptoms_list,
        "notes": str(notes).strip(),
        "weather_level": str(weather_level).strip().lower(),
        "event_time": str(event_time).strip() if event_time else submitted_at,

        # geo
        "geo_lat": str(geo_lat).strip() if geo_lat else "",
        "geo_lon": str(geo_lon).strip() if geo_lon else "",

        # evidence
        "reporter_image_name": image_name if image_name else None,
        "has_image": bool(image_name),

        # computed
        "severity_score": sev["severity_score"],
        "severity_level": sev["severity_level"],
        "urgency": sev["urgency"],

        # ngo workflow
        "status": "No Response",
        "ngo_note": "",
        "proof_image_name": None,
        "proof_location": "",
        "status_updated_at": None,
        "status_updated_by": "",
    }

    data["reports"].append(report)
    data["next_id"] = data.get("next_id", 1001) + 1
    write_json(_get_distress_file(), data)

    return report


# ─────────────────────────────────────────────────────────────
# Read helpers
# ─────────────────────────────────────────────────────────────

def get_all_reports_sorted() -> List[Dict[str, Any]]:
    reports = load_distress_reports()

    def _sort_key(r: Dict[str, Any]):
        severity_order = {
            "Critical": 4,
            "High": 3,
            "Moderate": 2,
            "Low": 1,
        }
        return (
            severity_order.get(r.get("severity_level", "Low"), 1),
            r.get("severity_score", 0),
            r.get("submitted_at", ""),
        )

    return sorted(reports, key=_sort_key, reverse=True)


def get_reports_for_user(username: str) -> List[Dict[str, Any]]:
    username = str(username).strip()
    reports = load_distress_reports()
    user_reports = [r for r in reports if r.get("reporter_username", "") == username]
    return sorted(user_reports, key=lambda r: r.get("submitted_at", ""), reverse=True)


def get_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    reports = load_distress_reports()
    for report in reports:
        if report.get("report_id") == report_id:
            return report
    return None


# ─────────────────────────────────────────────────────────────
# NGO updates ticket
# ─────────────────────────────────────────────────────────────

def update_report_status(
    report_id: str,
    status: str,
    ngo_username: str,
    ngo_note: Optional[str] = None,
    proof_image_name: Optional[str] = None,
    proof_location: Optional[str] = None,
) -> bool:
    """
    Update ticket status.
    Allowed statuses:
    - No Response
    - Acknowledged
    - On Hold
    - Action Taken

    If status == "Action Taken":
    - proof_image_name REQUIRED
    - proof_location REQUIRED
    """
    status = str(status).strip()

    allowed = {"No Response", "Acknowledged", "On Hold", "Action Taken"}
    if status not in allowed:
        return False

    if status == "Action Taken":
        if not proof_image_name or not str(proof_image_name).strip():
            return False
        if not proof_location or not str(proof_location).strip():
            return False

    data = read_json(_get_distress_file(), _default_payload())
    reports = data.get("reports", [])

    updated = False
    now = datetime.now().isoformat()

    for report in reports:
        if report.get("report_id") == report_id:
            report["status"] = status
            report["updated_at"] = now
            report["status_updated_at"] = now
            report["status_updated_by"] = str(ngo_username).strip()
            report["ngo_note"] = str(ngo_note).strip() if ngo_note else ""

            if status == "Action Taken":
                report["proof_image_name"] = str(proof_image_name).strip()
                report["proof_location"] = str(proof_location).strip()

            updated = True
            break

    if updated:
        write_json(_get_distress_file(), data)

    return updated