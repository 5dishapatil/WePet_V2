from django.db import models
from django.contrib.auth.models import User


class ShelterProfile(models.Model):
    """
    One NGO user = one shelter profile (MVP).
    Stores persistent shelter location so weather is fetched once for all animals.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="shelter_profile")
    shelter_name = models.CharField(max_length=120)
    location_label = models.CharField(max_length=255, blank=True)
    geo_lat = models.CharField(max_length=32, blank=True)
    geo_lon = models.CharField(max_length=32, blank=True)
    location_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.shelter_name or f"Shelter for {self.user.username}"


class AnimalGroup(models.Model):
    """
    NGO-side operational unit:
    Example: 4 Pugs in Kennel A1
    """
    SPECIES_CHOICES = [
        ("Dog", "Dog"),
        ("Cat", "Cat"),
        ("Other", "Other"),
    ]

    shelter = models.ForeignKey(
        ShelterProfile,
        on_delete=models.CASCADE,
        related_name="groups"
    )
    species = models.CharField(max_length=20, choices=SPECIES_CHOICES)
    breed_name = models.CharField(max_length=80)
    count = models.PositiveIntegerField(default=1)
    zone = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["species", "breed_name", "zone", "-created_at"]

    def __str__(self):
        return f"{self.breed_name} × {self.count} ({self.zone or 'Unassigned'})"