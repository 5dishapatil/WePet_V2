from django.contrib import admin
from community_app.models import TaskCompletion, RewardClaim


@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "task_id", "points", "location", "completed_at")
    list_filter = ("completed_at",)
    search_fields = ("user__username", "user__email", "task_id", "task_text", "location")
    ordering = ("-completed_at",)


@admin.register(RewardClaim)
class RewardClaimAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "reward_name",
        "voucher_amount",
        "milestone_points",
        "voucher_code",
        "status",
        "claimed_at",
    )
    list_filter = ("milestone_points", "status", "claimed_at")
    search_fields = ("user__username", "user__email", "reward_name", "voucher_code")
    ordering = ("-claimed_at",)
