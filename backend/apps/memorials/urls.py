from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.memorials import views

router = SimpleRouter()
router.register("memorials", views.MemorialViewSet, basename="memorial")

urlpatterns = [
    path(
        "memorials/<int:memorial_id>/photos/",
        views.PhotoListCreateView.as_view(),
        name="memorial-photos",
    ),
    path(
        "memorials/<int:memorial_id>/photos/reorder/",
        views.PhotoReorderView.as_view(),
        name="memorial-photos-reorder",
    ),
    path(
        "memorials/<int:memorial_id>/photos/<int:pk>/",
        views.PhotoDetailView.as_view(),
        name="memorial-photo-detail",
    ),
    *router.urls,
]
