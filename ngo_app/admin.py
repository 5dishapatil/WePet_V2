from django.contrib import admin
from ngo_app.models import ShelterProfile, AnimalGroup


@admin.register(ShelterProfile)
class ShelterProfileAdmin(admin.ModelAdmin):
    list_display = ("shelter_name", "user", "location_label", "location_locked", "updated_at")
    search_fields = ("shelter_name", "user__username", "location_label")


@admin.register(AnimalGroup)
class AnimalGroupAdmin(admin.ModelAdmin):
    list_display = ("breed_name", "species", "count", "zone", "shelter", "updated_at")
    list_filter = ("species",)
    search_fields = ("breed_name", "zone", "shelter__shelter_name", "shelter__user__username")