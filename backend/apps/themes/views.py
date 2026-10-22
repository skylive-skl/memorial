from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.themes.models import Theme
from apps.themes.serializers import ThemeSerializer


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("category", enum=Theme.Category.values, required=False)]
    )
)
class ThemeViewSet(viewsets.ReadOnlyModelViewSet):
    """Каталог активных тем. Публичный: данные тем не персональные."""

    serializer_class = ThemeSerializer
    permission_classes = (AllowAny,)
    lookup_field = "key"

    def get_queryset(self):
        queryset = Theme.objects.filter(is_active=True).prefetch_related("assets")
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        return queryset
