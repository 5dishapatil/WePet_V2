"""wepet_project/urls.py — Root URL configuration."""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("pets/", include("pets.urls")),
    path("community/", include("community_app.urls")),
    path("ngo/", include("ngo_app.urls")),
    # Root → redirect to pet owner (login required; handled there)
    path("", RedirectView.as_view(url="/pets/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)