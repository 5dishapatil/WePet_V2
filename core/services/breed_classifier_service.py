"""
core/services/breed_classifier_service.py — MobileNetV3 breed classifier for WePet.
Migrated from services/breed_classifier_service.py — logic unchanged.
st.cache_resource replaced with module-level lazy singleton for Django compatibility.
"""
import io
from pathlib import Path
from django.conf import settings

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_SIZE = 224
UNKNOWN_THRESHOLD = 0.35

# ─── Breed groups (unchanged) ─────────────────────────────────────────────────
CAT_BREEDS = {
    "abyssinian", "bengal", "birman", "bombay", "british_shorthair",
    "egyptian_mau", "maine_coon", "persian", "ragdoll", "russian_blue",
    "siamese", "sphynx",
}

DOG_BREEDS = {
    "american_bulldog", "american_pit_bull_terrier", "basset_hound", "beagle",
    "boxer", "chihuahua", "english_cocker_spaniel", "english_setter",
    "german_shorthaired", "great_pyrenees", "havanese", "japanese_chin",
    "keeshond", "leonberger", "miniature_pinscher", "newfoundland",
    "pomeranian", "pug", "saint_bernard", "samoyed", "scottish_terrier",
    "shiba_inu", "staffordshire_bull_terrier", "wheaten_terrier", "yorkshire_terrier",
}

MODEL_TO_PROFILE_NAME = {
    "pug": "Pug",
    "persian": "Persian",
    "maine_coon": "Maine Coon",
    "siamese": "Siamese",
    "british_shorthair": "British Shorthair",
    "sphynx": "Sphynx",
}

_predict_transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# ─── Module-level lazy singleton (replaces @st.cache_resource) ────────────────
_model = None
_class_names = None


def _get_model_path() -> Path:
    return settings.FINETUNING_DIR / "mobilenetv3_pet_best.pth"


def load_breed_model():
    """Load model once per process lifetime (lazy singleton)."""
    global _model, _class_names
    if _model is not None:
        return _model, _class_names

    model_path = _get_model_path()
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    checkpoint = torch.load(model_path, map_location=DEVICE)
    class_names = checkpoint["class_names"]
    num_classes = len(class_names)

    model = models.mobilenet_v3_small(weights=None)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(DEVICE)
    model.eval()

    _model = model
    _class_names = class_names
    return _model, _class_names


def _pretty_label(model_breed: str) -> str:
    return model_breed.replace("_", " ").title()


def _species_from_breed(model_breed: str) -> str:
    if model_breed in CAT_BREEDS:
        return "Cat"
    if model_breed in DOG_BREEDS:
        return "Dog"
    return "Unknown"


def predict_from_bytes(image_bytes: bytes) -> dict:
    """
    Accept raw bytes of an uploaded image.
    Returns the same dict schema as original predict_uploaded_pet().
    """
    try:
        model, class_names = load_breed_model()

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        input_tensor = _predict_transform(image).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            outputs = model(input_tensor)
            probs = torch.softmax(outputs, dim=1)
            top3_probs, top3_indices = torch.topk(probs, 3, dim=1)

        top3_probs = top3_probs[0].detach().cpu().numpy()
        top3_indices = top3_indices[0].detach().cpu().numpy()

        top3 = []
        for idx, prob in zip(top3_indices, top3_probs):
            model_breed = class_names[idx]
            top3.append({
                "breed": model_breed,
                "display": _pretty_label(model_breed),
                "confidence": float(prob),
            })

        best_idx = int(top3_indices[0])
        best_prob = float(top3_probs[0])
        best_model_breed = class_names[best_idx]
        species = _species_from_breed(best_model_breed)
        display_breed = _pretty_label(best_model_breed)

        if best_prob < UNKNOWN_THRESHOLD:
            return {
                "success": False,
                "status": "unknown",
                "species": "Unknown",
                "model_breed": best_model_breed,
                "display_breed": display_breed,
                "mapped_profile_breed": None,
                "confidence": best_prob,
                "top3": top3,
                "message": "Could not confidently identify this pet from the supported trained classes.",
            }

        mapped_profile_breed = MODEL_TO_PROFILE_NAME.get(best_model_breed)

        if not mapped_profile_breed:
            return {
                "success": True,
                "status": "unsupported_profile",
                "species": species,
                "model_breed": best_model_breed,
                "display_breed": display_breed,
                "mapped_profile_breed": None,
                "confidence": best_prob,
                "top3": top3,
                "message": "Breed detected, but this breed is not yet supported by the weather-risk MVP profiles.",
            }

        return {
            "success": True,
            "status": "ok",
            "species": species,
            "model_breed": best_model_breed,
            "display_breed": display_breed,
            "mapped_profile_breed": mapped_profile_breed,
            "confidence": best_prob,
            "top3": top3,
            "message": "Breed identified successfully.",
        }

    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "species": "Unknown",
            "model_breed": None,
            "display_breed": None,
            "mapped_profile_breed": None,
            "confidence": 0.0,
            "top3": [],
            "message": f"Breed detection failed: {str(e)}",
        }