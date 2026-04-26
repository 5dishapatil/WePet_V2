"""pets/urls.py"""
from django.urls import path
from pets import views

app_name = "pets"

urlpatterns = [
    path("", views.pet_owner_view, name="pet_owner"),
    path("analyze/", views.analyze_view, name="analyze"),
    path("save-pet/", views.save_pet_view, name="save_pet"),
    path("delete-pet/<int:pet_id>/", views.delete_pet_view, name="delete_pet"),
    path("detect-breed/", views.detect_breed_view, name="detect_breed"),
    path("clear-results/", views.clear_results_view, name="clear_results"),
]