from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

# Re-register the default User with the default UserAdmin (safe no-op if already registered)
try:
    admin.site.unregister(User)
    admin.site.register(User, UserAdmin)
except Exception:
    pass