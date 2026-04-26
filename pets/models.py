"""pets/models.py — Pet profiles and risk history for WePet."""
from django.db import models
from django.contrib.auth.models import User


class Pet(models.Model):
    AGE_CHOICES = [("Young", "Young"), ("Adult", "Adult"), ("Senior", "Senior")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pets")
    pet_name = models.CharField(max_length=100)
    species = models.CharField(max_length=20)   # Dog / Cat
    breed = models.CharField(max_length=100)
    age_group = models.CharField(max_length=20, choices=AGE_CHOICES, default="Adult")
    overweight = models.BooleanField(default=False)
    heat_sensitive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pet_name} ({self.breed})"

    def to_dict(self):
        return {
            "pet_id": self.pk,
            "user_id": self.user_id,
            "pet_name": self.pet_name,
            "species": self.species,
            "breed": self.breed,
            "age_group": self.age_group,
            "overweight": self.overweight,
            "heat_sensitive": self.heat_sensitive,
        }


class RiskHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="risk_history")
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="risk_history")
    location = models.CharField(max_length=255)
    temperature = models.FloatField()
    apparent_temperature = models.FloatField()
    humidity = models.IntegerField()
    risk_score = models.FloatField()
    risk_level = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]