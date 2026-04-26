from django import forms
from ngo_app.models import ShelterProfile, AnimalGroup
from core.services.breed_profile_service import get_dog_breeds, get_cat_breeds


DOG_BREEDS = get_dog_breeds()
CAT_BREEDS = get_cat_breeds()

ALL_BREED_CHOICES = [("", "Select breed")] + \
    [(b, f"Dog — {b}") for b in DOG_BREEDS] + \
    [(b, f"Cat — {b}") for b in CAT_BREEDS]


class ShelterProfileForm(forms.ModelForm):
    class Meta:
        model = ShelterProfile
        fields = ["shelter_name", "location_label", "geo_lat", "geo_lon"]
        widgets = {
            "shelter_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. PawCare Shelter Pune"
            }),
            "location_label": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Pune, Maharashtra, India"
            }),
            "geo_lat": forms.HiddenInput(),
            "geo_lon": forms.HiddenInput(),
        }


class AnimalGroupForm(forms.ModelForm):
    # Hidden detection fields (NOT model fields)
    detected_species = forms.CharField(required=False, widget=forms.HiddenInput())
    detected_breed = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = AnimalGroup
        fields = ["species", "breed_name", "count", "zone", "notes"]
        widgets = {
            "species": forms.Select(attrs={"class": "form-select", "id": "id_species"}),
            "breed_name": forms.Select(
                choices=ALL_BREED_CHOICES,
                attrs={"class": "form-select", "id": "id_breed_name"}
            ),
            "count": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 1,
                "placeholder": "e.g. 4"
            }),
            "zone": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Kennel A1 / Cat Room 2"
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "rows": 3,
                "placeholder": "Optional notes — vulnerable animals, medication, rescue condition, etc."
            }),
        }

    def clean(self):
        cleaned = super().clean()

        species = cleaned.get("species")
        breed = cleaned.get("breed_name")
        detected_species = cleaned.get("detected_species", "").strip()
        detected_breed = cleaned.get("detected_breed", "").strip()

        # PRIORITY: detected breed should override manual if present
        if detected_breed:
            breed = detected_breed
            cleaned["breed_name"] = detected_breed

            if detected_species in ["Dog", "Cat"]:
                species = detected_species
                cleaned["species"] = detected_species

        if not species or species not in ["Dog", "Cat"]:
            self.add_error("species", "Please choose a valid species.")
            return cleaned

        if not breed:
            self.add_error("breed_name", "Please choose a supported breed or use image detection.")
            return cleaned

        if species == "Dog" and breed not in DOG_BREEDS:
            self.add_error("breed_name", "Please choose a supported dog breed.")
        elif species == "Cat" and breed not in CAT_BREEDS:
            self.add_error("breed_name", "Please choose a supported cat breed.")

        return cleaned