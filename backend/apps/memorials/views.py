from django.conf import settings
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.memorials import qr
from apps.memorials.models import Memorial, Photo
from apps.memorials.serializers import (
    MemorialSerializer,
    PhotoSerializer,
    PhotoUploadSerializer,
    PublicMemorialSerializer,
)
from apps.memorials.tasks import process_photo


class MemorialViewSet(viewsets.ModelViewSet):
    """Страницы текущего пользователя. Чужая страница → 404."""

    serializer_class = MemorialSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # генерация OpenAPI-схемы
            return Memorial.objects.none()
        return (
            Memorial.objects.filter(owner=self.request.user)
            .select_related("theme")
            .prefetch_related("photos")
        )

    def perform_create(self, serializer: MemorialSerializer) -> None:
        serializer.save(owner=self.request.user)

    @extend_schema(request=None, responses=MemorialSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        memorial = self.get_object()
        memorial.publish()
        return Response(self.get_serializer(memorial).data)

    @extend_schema(
        parameters=[OpenApiParameter("format", enum=["svg", "png"], default="svg")],
        responses={
            (200, "image/svg+xml"): OpenApiResponse(OpenApiTypes.BINARY),
            (200, "image/png"): OpenApiResponse(OpenApiTypes.BINARY),
        },
    )
    @action(detail=True, methods=["get"])
    def qr(self, request: Request, pk: str | None = None) -> HttpResponse:
        """QR со ссылкой {PUBLIC_BASE_URL}/m/{short_code}: SVG (вектор) или PNG для печати."""
        memorial = self.get_object()
        image_format = request.query_params.get("format", "svg")
        if image_format == "svg":
            content, content_type = qr.render_svg(memorial.short_code), "image/svg+xml"
        elif image_format == "png":
            content, content_type = qr.render_png(memorial.short_code), "image/png"
        else:
            raise ValidationError({"format": "Expected 'svg' or 'png'."})
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = (
            f'inline; filename="memorial-{memorial.short_code}-qr.{image_format}"'
        )
        # short_code неизменяем — QR тоже; private: эндпоинт только для владельца.
        response["Cache-Control"] = "private, max-age=86400"
        return response

    @extend_schema(request=None, responses=MemorialSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request: Request, pk: str | None = None) -> Response:
        memorial = self.get_object()
        memorial.unpublish()
        return Response(self.get_serializer(memorial).data)


class MemorialPhotosMixin:
    """Фото только своей страницы: чужая страница или чужое фото → 404."""

    def get_memorial(self) -> Memorial:
        return get_object_or_404(Memorial, pk=self.kwargs["memorial_id"], owner=self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Photo.objects.none()
        return Photo.objects.filter(
            memorial_id=self.kwargs["memorial_id"], memorial__owner=self.request.user
        )


class PhotoListCreateView(MemorialPhotosMixin, generics.ListAPIView):
    serializer_class = PhotoSerializer
    parser_classes = (MultiPartParser, FormParser)

    def list(self, request: Request, *args, **kwargs) -> Response:
        self.get_memorial()  # 404 для чужой страницы
        return super().list(request, *args, **kwargs)

    @extend_schema(request=PhotoUploadSerializer, responses={201: PhotoSerializer})
    def post(self, request: Request, memorial_id: int) -> Response:
        memorial = self.get_memorial()
        upload = PhotoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)

        with transaction.atomic():
            # Блокировка страницы: лимит и порядок считаются без гонок.
            memorial = Memorial.objects.select_for_update().get(pk=memorial.pk)
            photos = memorial.photos.all()
            if photos.count() >= settings.PHOTO_MAX_PER_MEMORIAL:
                raise ValidationError(
                    {"file": f"A page can have at most {settings.PHOTO_MAX_PER_MEMORIAL} photos."},
                    code="photo_limit",
                )
            last_order = photos.aggregate(value=Max("order"))["value"]
            photo = Photo(
                memorial=memorial,
                caption=upload.validated_data.get("caption", ""),
                order=0 if last_order is None else last_order + 1,
                is_cover=not photos.filter(is_cover=True).exists(),
            )
            photo.original.save(upload.validated_data["file"].name, upload.validated_data["file"])
            transaction.on_commit(lambda: process_photo.delay(photo.pk))

        return Response(PhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class PhotoDetailView(MemorialPhotosMixin, generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = PhotoSerializer
    http_method_names = ("patch", "delete", "options")

    @transaction.atomic
    def perform_update(self, serializer: PhotoSerializer) -> None:
        if serializer.validated_data.get("is_cover"):
            # Сначала снимаем cover с остальных: в БД «не больше одной обложки».
            Photo.objects.filter(memorial_id=serializer.instance.memorial_id).exclude(
                pk=serializer.instance.pk
            ).update(is_cover=False)
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, photo: Photo) -> None:
        was_cover = photo.is_cover
        memorial_id = photo.memorial_id
        photo.delete()
        if was_cover:
            next_cover = Photo.objects.filter(memorial_id=memorial_id).first()
            if next_cover is not None:
                next_cover.is_cover = True
                next_cover.save(update_fields=["is_cover"])


class PhotoReorderView(MemorialPhotosMixin, generics.GenericAPIView):
    serializer_class = PhotoSerializer

    @extend_schema(
        request={"application/json": {"type": "array", "items": {"type": "integer"}}},
        responses=PhotoSerializer(many=True),
    )
    @transaction.atomic
    def patch(self, request: Request, memorial_id: int) -> Response:
        memorial = self.get_memorial()
        ids = serializers.ListField(child=serializers.IntegerField()).run_validation(request.data)
        photos = {photo.pk: photo for photo in memorial.photos.select_for_update()}
        if len(ids) != len(set(ids)) or set(ids) != set(photos):
            raise ValidationError("Expected every photo id of this page exactly once.")
        for index, photo_id in enumerate(ids):
            photos[photo_id].order = index
        Photo.objects.bulk_update(photos.values(), ["order"])
        return Response(PhotoSerializer(memorial.photos.all(), many=True).data)


class PublicMemorialView(generics.RetrieveAPIView):
    """Опубликованная страница по short_code — для публичной страницы /m/{code}.

    Черновик и несуществующий код дают одинаковый 404: не раскрываем, что страница есть.
    """

    serializer_class = PublicMemorialSerializer
    # Без аутентификации: протухшая auth-cookie посетителя не должна давать 401.
    authentication_classes = ()
    permission_classes = (AllowAny,)
    lookup_field = "short_code"

    def get_queryset(self):
        return (
            Memorial.objects.filter(status=Memorial.Status.PUBLISHED)
            .select_related("theme")
            .prefetch_related(
                "theme__assets",
                Prefetch(
                    "photos",
                    queryset=Photo.objects.filter(processing_status=Photo.ProcessingStatus.READY),
                    to_attr="ready_photos",
                ),
            )
        )

    def get_object(self) -> Memorial:
        try:
            return super().get_object()
        except Http404:
            raise NotFound() from None  # общий текст, без имени модели
