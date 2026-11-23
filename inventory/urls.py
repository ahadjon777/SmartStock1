from django.urls import path

from . import views

urlpatterns = [
    path("", views.scan, name="scan"),
    path("api/scan/", views.scan_api, name="scan_api"),
    path("stats/", views.dashboard, name="dashboard"),
]
