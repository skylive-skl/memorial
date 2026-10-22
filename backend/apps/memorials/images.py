"""Проверка загружаемых фото и генерация вариантов."""

import io
from typing import IO

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

# Как их называет Pillow (HEIC открывается через pillow-heif как HEIF).
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}


class UnsupportedImage(ValueError):
    pass


def detect_format(file: IO[bytes]) -> str:
    """Формат по содержимому, а не по расширению. Бросает UnsupportedImage."""
    try:
        with Image.open(file) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise UnsupportedImage("File is not a valid image.") from exc
    finally:
        file.seek(0)
    if image_format not in ALLOWED_FORMATS:
        raise UnsupportedImage(f"Unsupported image format: {image_format}.")
    return image_format


def make_variants(file: IO[bytes]) -> tuple[int, int, dict[str, bytes]]:
    """Размеры повёрнутого по EXIF оригинала и варианты WebP.

    Варианты перекодируются без EXIF — геоданные и прочие метаданные не попадают наружу.
    """
    with Image.open(file) as source:
        image = ImageOps.exif_transpose(source)
    image = image.convert("RGBA" if _has_alpha(image) else "RGB")
    # Метаданные (exif, xmp — в обоих бывают GPS) не переносим; ICC — только цвет.
    icc_profile = image.info.get("icc_profile")
    image.info = {}
    width, height = image.size

    variants = {}
    for name, size in settings.PHOTO_VARIANTS.items():
        variant = image.copy()
        variant.thumbnail((size, size), Image.Resampling.LANCZOS)  # не увеличивает
        buffer = io.BytesIO()
        variant.save(
            buffer,
            format="WEBP",
            quality=settings.PHOTO_WEBP_QUALITY,
            icc_profile=icc_profile,
            exif=b"",
            xmp=b"",
        )
        variants[name] = buffer.getvalue()
    return width, height, variants


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
