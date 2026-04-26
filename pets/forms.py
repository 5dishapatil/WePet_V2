"""
pets/forms.py — Optional Django forms for Pet Owner module.
Current views still use manual request.POST parsing to preserve Streamlit logic,
but these forms provide structure and future validation.
"""

from django import forms


class PetProfileForm(forms.Form):
    SPECIES_CHOICES = [
        ("Dog", "Dog"),
        ("Cat", "Cat"),
        ("Don't know", "Don't know"),
    ]

    AGE_CHOICES = [
        ("Young", "Young"),
        ("Adult", "Adult"),
        ("Senior", "Senior"),
    ]

    pet_name = forms.CharField(max_length=100, required=False)
    species = forms.ChoiceField(choices=SPECIES_CHOICES, required=True)
    breed_name = forms.CharField(max_length=100, required=False)
    age_group = forms.ChoiceField(choices=AGE_CHOICES, required=True)
    overweight = forms.BooleanField(required=False)
    heat_sensitive = forms.BooleanField(required=False)

    location_mode = forms.ChoiceField(
        choices=[("gps", "Use current location"), ("manual", "Enter manually")],
        required=True,
        initial="manual",
    )
    location_text = forms.CharField(max_length=255, required=False)

    geo_lat = forms.CharField(required=False)
    geo_lon = forms.CharField(required=False)
    location_label = forms.CharField(required=False)

    selected_pet_id = forms.CharField(required=False)


class BreedDetectionForm(forms.Form):
    pet_image = forms.ImageField(required=True)