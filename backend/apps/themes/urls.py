from rest_framework.routers import SimpleRouter

from apps.themes.views import ThemeViewSet

router = SimpleRouter()
router.register("themes", ThemeViewSet, basename="theme")

urlpatterns = router.urls
