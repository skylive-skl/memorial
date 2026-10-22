from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.memorials.models import Memorial, Photo
from apps.memorials.serializers import MemorialSerializer, PhotoSerializer, PhotoUploadSerializer
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
