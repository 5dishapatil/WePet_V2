"""
community_app/urls.py — URL patterns for WePet community app.
Supports:
- Community task flow
- Distress report submission by community users
- Rewards page + reward claims
"""
from django.urls import path
from community_app import views

app_name = "community"

urlpatterns = [
    # Main community page
    path("", views.community_view, name="community"),

    # Task actions
    path("fetch-task/", views.fetch_task_view, name="fetch_task"),
    path("complete-task/", views.complete_task_view, name="complete_task"),

    # Community distress submission
    path("submit-distress/", views.submit_distress_view, name="submit_distress"),

    # Rewards
    path("rewards/", views.rewards_view, name="rewards"),
    path("claim-reward/<int:milestone>/", views.claim_reward_view, name="claim_reward"),
]
