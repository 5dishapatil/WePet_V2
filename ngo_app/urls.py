from django.urls import path
from ngo_app import views

app_name = "ngo"

urlpatterns = [
    path("", views.ngo_view, name="ngo"),
    path("save-location/", views.save_shelter_location_view, name="save_location"),
    path("add-group/", views.add_group_view, name="add_group"),
    path("delete-group/<int:group_id>/", views.delete_group_view, name="delete_group"),
    path("update-report/<str:report_id>/", views.update_report_view, name="update_report"),

    # NEW: NGO breed detection endpoint
    path("detect-breed/", views.ngo_detect_breed_view, name="detect_breed"),
]