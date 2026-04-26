"""
community_app/models.py — Community task completion tracking for WePet.
"""
from django.db import models
from django.contrib.auth.models import User


class TaskCompletion(models.Model):
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
        return f"{self.user} — {self.task_id} (+{self.points} pts)"