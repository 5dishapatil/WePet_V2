"""
core/services/storage_service.py — Low-level JSON read/write helpers for WePet MVP.
Django migration version.

IMPORTANT:
- This file should ONLY contain generic file persistence helpers.
- Business logic (distress reports, community tasks, etc.) must live in their own services.
"""

import json
from pathlib import Path
from typing import Any, Dict


def ensure_json_file(path: Path, default: Dict[str, Any]) -> None:
    """
    Ensure a JSON file exists. If not, create it with the given default payload.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


def read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely read a JSON file.
    If file doesn't exist or is corrupted, return the provided default.
    """
    ensure_json_file(path, default)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return default
    except (json.JSONDecodeError, IOError, OSError):
        return default


def write_json(path: Path, data: Dict[str, Any]) -> bool:
    """
    Safely write JSON data to disk.
    Returns True if successful, False otherwise.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        return True
    except (IOError, OSError):
        return False