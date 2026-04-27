"""
community_app/models.py — Community task completion + rewards tracking for WePet.
Tracks:
1. Community task completions (points earning)
2. Simulated reward claims (fake Amazon cash vouchers)
"""
from django.db import models
from django.contrib.auth.models import User


class TaskCompletion(models.Model):
    """
    Stores each completed community task and the points earned by the user.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_completions",
    )
    task_id = models.CharField(max_length=64, default="default")
    task_text = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=10)
    location = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completed_at"]

    def __str__(self):
        user_display = self.user.username if self.user else "Anonymous"
        return f"{user_display} — {self.task_id} (+{self.points} pts)"


class RewardClaim(models.Model):
    """
    Stores simulated reward claims for community users.

    Example milestones:
    - 100 points  -> ₹50 voucher
    - 250 points  -> ₹150 voucher
    - 500 points  -> ₹400 voucher
    - 1000 points -> ₹1000 voucher

    IMPORTANT:
    - This is a simulated reward system only (demo / MVP).
    - No real Amazon or payment integration.
    - Each milestone can be claimed only once per user.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reward_claims",
    )

    # Milestone threshold at which reward was unlocked/claimed
    milestone_points = models.PositiveIntegerField()

    # Display name shown in UI
    reward_name = models.CharField(max_length=120)

    # Simulated voucher amount (₹50, ₹150, ₹400, ₹1000, etc.)
    voucher_amount = models.PositiveIntegerField(default=0)

    # Fake generated code like: AMZ-50-X8KQ9P2M
    voucher_code = models.CharField(max_length=64, unique=True)

    # Optional status field for future extensibility
    status = models.CharField(
        max_length=20,
        choices=[
            ("claimed", "Claimed"),
        ],
        default="claimed",
    )

    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-claimed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "milestone_points"],
                name="unique_reward_claim_per_user_per_milestone",
            )
        ]

    def __str__(self):
        return (
            f"{self.user.username} — {self.reward_name} "
            f"(₹{self.voucher_amount}, {self.milestone_points} pts)"
        )
