import io

import pytest
from PIL import Image

from apps.memorials.images import UnsupportedImage, detect_format, make_variants
from apps.memorials.tests.images import ORIENTATION_ROTATE_90_CW, image_bytes, jpeg_bytes


@pytest.mark.parametrize(
    ("fmt", "expected"), [("JPEG", "JPEG"), ("PNG", "PNG"), ("WEBP", "WEBP"), ("HEIF", "HEIF")]
)
def test_detect_supported_formats(fmt, expected):
    assert detect_format(io.BytesIO(image_bytes(fmt))) == expected


def test_detect_rejects_unsupported_format():
    with pytest.raises(UnsupportedImage, match="GIF"):
        detect_format(io.BytesIO(image_bytes("GIF")))


@pytest.mark.parametrize("content", [b"not an image", b"\xff\xd8\xff\xe0broken jpeg"])
def test_detect_rejects_non_images(content):
    with pytest.raises(UnsupportedImage):
        detect_format(io.BytesIO(content))


def test_detect_rewinds_file():
    file = io.BytesIO(image_bytes("PNG"))

    detect_format(file)

    assert file.tell() == 0


def test_variants_sizes_and_format(settings):
    settings.PHOTO_VARIANTS = {"thumb": 100, "large": 300}

    width, height, variants = make_variants(io.BytesIO(jpeg_bytes((400, 200))))

    assert (width, height) == (400, 200)
    sizes = {name: Image.open(io.BytesIO(data)).size for name, data in variants.items()}
    assert sizes == {"thumb": (100, 50), "large": (300, 150)}
    assert all(Image.open(io.BytesIO(d)).format == "WEBP" for d in variants.values())


def test_small_image_is_not_upscaled(settings):
    settings.PHOTO_VARIANTS = {"large": 2048}

    _, _, variants = make_variants(io.BytesIO(jpeg_bytes((400, 200))))

    assert Image.open(io.BytesIO(variants["large"])).size == (400, 200)


def test_exif_orientation_applied(settings):
    settings.PHOTO_VARIANTS = {"thumb": 100}
    source = jpeg_bytes((400, 200), orientation=ORIENTATION_ROTATE_90_CW)

    width, height, variants = make_variants(io.BytesIO(source))

    assert (width, height) == (200, 400)
    assert Image.open(io.BytesIO(variants["thumb"])).size == (50, 100)


def test_variants_have_no_exif_or_gps():
    source = jpeg_bytes(gps=True, orientation=ORIENTATION_ROTATE_90_CW)
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(0x8825)  # GPS в исходнике есть

    _, _, variants = make_variants(io.BytesIO(source))

    for data in variants.values():
        variant = Image.open(io.BytesIO(data))
        assert not variant.getexif()
        assert "exif" not in variant.info
        assert "xmp" not in variant.info
        assert b"GPS" not in data


def test_transparency_preserved():
    _, _, variants = make_variants(io.BytesIO(image_bytes("PNG", mode="RGBA")))

    assert Image.open(io.BytesIO(variants["thumb"])).mode == "RGBA"


def test_heic_source():
    width, height, variants = make_variants(io.BytesIO(image_bytes("HEIF", size=(64, 48))))

    assert (width, height) == (64, 48)
    assert set(variants) == {"thumb", "medium", "large"}
