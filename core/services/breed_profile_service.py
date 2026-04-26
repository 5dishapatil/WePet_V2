"""
core/services/breed_profile_service.py — Load and serve breed profile data.
Migrated from services/breed_profile_service.py — logic unchanged.
Path resolution updated for Django BASE_DIR.
"""
import json
from pathlib import Path
from django.conf import settings

_DOG_BREEDS = [
    "German Shepherd",
    "Labrador Retriever",
    "Golden Retriever",
    "Pug",
    "Siberian Husky",
]

_CAT_BREEDS = [
    "Persian",
    "Maine Coon",
    "Siamese",
    "British Shorthair",
    "Sphynx",
]

_profiles_cache = None


def _get_profiles_path() -> Path:
    return settings.DATA_DIR / "breed_profiles.json"


def _load_profiles() -> dict:
    global _profiles_cache
    if _profiles_cache is None:
        with open(_get_profiles_path(), "r") as f:
            _profiles_cache = json.load(f)
    return _profiles_cache


def get_dog_breeds() -> list:
    return _DOG_BREEDS


def get_cat_breeds() -> list:
    return _CAT_BREEDS


def get_breed_profile(breed_name: str) -> dict:
    profiles = _load_profiles()
    profile = profiles.get(breed_name)
    if not profile:
        raise ValueError(f"Breed '{breed_name}' not supported in this MVP.")
    profile.setdefault("sun_exposure_sensitivity", 0.0)
    return profile


def get_all_profiles() -> dict:
    return _load_profiles()