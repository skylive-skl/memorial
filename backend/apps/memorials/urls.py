from rest_framework.routers import SimpleRouter

from apps.memorials.views import MemorialViewSet

router = SimpleRouter()
router.register("memorials", MemorialViewSet, basename="memorial")

urlpatterns = router.urls
