"""QR-код страницы для гравировки на памятнике."""

import io

import segno
from django.conf import settings

# Коррекция ошибок H (~30%): код читается даже с частично повреждённой поверхностью камня.
ERROR_CORRECTION = "h"
QUIET_ZONE = 4  # модуля — минимум по стандарту
# PNG для печати: 20 px на модуль и 300 dpi в метаданных
# (код ~41 модуль с полями → ~820 px ≈ 7 см при 300 dpi).
PNG_SCALE = 20
PNG_DPI = 300


def public_url(short_code: str) -> str:
    return f"{settings.PUBLIC_BASE_URL}/m/{short_code}"


def make_qr(short_code: str) -> segno.QRCode:
    # boost_error=False: уровень строго H, segno не будет его менять.
    return segno.make_qr(public_url(short_code), error=ERROR_CORRECTION, boost_error=False)


def render_svg(short_code: str) -> bytes:
    buffer = io.BytesIO()
    # Вектор: масштаб и единицы не важны, viewBox — в модулях.
    make_qr(short_code).save(
        buffer, kind="svg", border=QUIET_ZONE, xmldecl=True, svgns=True, omitsize=True
    )
    return buffer.getvalue()


def render_png(short_code: str) -> bytes:
    buffer = io.BytesIO()
    make_qr(short_code).save(buffer, kind="png", scale=PNG_SCALE, border=QUIET_ZONE, dpi=PNG_DPI)
    return buffer.getvalue()
