from django.urls import path
from community_app import views

app_name = "community"

urlpatterns = [
    path("", views.community_view, name="community"),
    path("fetch-task/", views.fetch_task_view, name="fetch_task"),
    path("complete-task/", views.complete_task_view, name="complete_task"),
    path("submit-distress/", views.submit_distress_view, name="submit_distress"),
]