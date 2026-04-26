from django.contrib import admin
from pets.models import Pet, RiskHistory


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display  = ("pet_name", "species", "breed", "age_group", "user", "created_at")
    list_filter   = ("species", "age_group", "overweight", "heat_sensitive")
    search_fields = ("pet_name", "breed", "user__email")
    ordering      = ("-created_at",)


@admin.register(RiskHistory)
class RiskHistoryAdmin(admin.ModelAdmin):
    list_display = ("pet", "user", "risk_level", "risk_score", "location", "created_at")
    list_filter  = ("risk_level",)
    ordering     = ("-created_at",)