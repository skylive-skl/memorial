from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.memorials.models import Memorial
from apps.memorials.serializers import MemorialSerializer


class MemorialViewSet(viewsets.ModelViewSet):
    """Страницы текущего пользователя. Чужая страница → 404."""

    serializer_class = MemorialSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # генерация OpenAPI-схемы
            return Memorial.objects.none()
        return Memorial.objects.filter(owner=self.request.user).select_related("theme")

    def perform_create(self, serializer: MemorialSerializer) -> None:
        serializer.save(owner=self.request.user)

    @extend_schema(request=None, responses=MemorialSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        memorial = self.get_object()
        memorial.publish()
        return Response(self.get_serializer(memorial).data)

    @extend_schema(request=None, responses=MemorialSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request: Request, pk: str | None = None) -> Response:
        memorial = self.get_object()
        memorial.unpublish()
        return Response(self.get_serializer(memorial).data)
