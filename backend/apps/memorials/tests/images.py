"""Генерация тестовых изображений."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import ExifTags, Image

ORIENTATION_ROTATE_90_CW = 6


def jpeg_bytes(size=(400, 200), *, orientation: int | None = None, gps: bool = False) -> bytes:
    exif = Image.Exif()
    if orientation:
        exif[ExifTags.Base.Orientation] = orientation
    if gps:
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps_ifd[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps_ifd[ExifTags.GPS.GPSLatitude] = (41.0, 18.0, 0.0)
        gps_ifd[ExifTags.GPS.GPSLongitudeRef] = "E"
        gps_ifd[ExifTags.GPS.GPSLongitude] = (69.0, 16.0, 0.0)
    buffer = io.BytesIO()
    Image.new("RGB", size, "teal").save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def image_bytes(fmt: str, size=(64, 48), mode="RGB") -> bytes:
    if fmt == "HEIF":
        from pillow_heif import register_heif_opener

        register_heif_opener()
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 100, 50, 128) if mode == "RGBA" else "orange").save(
        buffer, format=fmt
    )
    return buffer.getvalue()


def upload(name: str, content: bytes, content_type: str = "image/jpeg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)
