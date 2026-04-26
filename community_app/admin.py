from django.contrib import admin
from community_app.models import TaskCompletion


@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "task_id", "points", "location", "completed_at")
    ordering     = ("-completed_at",)