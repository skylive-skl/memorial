import io
import re
import xml.etree.ElementTree as ET

import pytest
import zxingcpp
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.memorials import qr
from apps.memorials.tests.factories import MemorialFactory

SVG_NS = "{http://www.w3.org/2000/svg}"


def decode(image: Image.Image) -> zxingcpp.Barcode:
    results = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode)
    assert len(results) == 1
    return results[0]


def rasterize_segno_svg(svg: bytes, scale: int = 10) -> Image.Image:
    """Минимальный растеризатор SVG от segno: путь из M/m-переходов и h-линий по модулям."""
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    width, height = (int(v) for v in root.attrib["viewBox"].split()[2:])
    path = root.find(f"{SVG_NS}path").attrib["d"]
    image = Image.new("L", (width * scale, height * scale), 255)
    x = y = 0.0
    for command, a, b in re.findall(r"([Mmh])(-?[\d.]+)(?: (-?[\d.]+))?", path):
        if command == "M":
            x, y = float(a), float(b)
        elif command == "m":
            x, y = x + float(a), y + float(b)
        else:  # h: тёмная полоса длиной a модулей в строке int(y)
            row = int(y)
            for col in range(int(x), int(x + float(a))):
                image.paste(0, (col * scale, row * scale, (col + 1) * scale, (row + 1) * scale))
            x += float(a)
    return image


@pytest.fixture(autouse=True)
def public_base_url(settings):
    settings.PUBLIC_BASE_URL = "https://memorial.example"


class TestRender:
    def test_png_decodes_to_public_url(self):
        image = Image.open(io.BytesIO(qr.render_png("JGwYFNzK")))

        result = decode(image)

        assert result.text == "https://memorial.example/m/JGwYFNzK"
        assert result.ec_level == "H"

    def test_png_is_print_quality(self):
        image = Image.open(io.BytesIO(qr.render_png("JGwYFNzK")))

        assert image.format == "PNG"
        assert min(image.size) >= 600
        assert tuple(round(v) for v in image.info["dpi"]) == (300, 300)

    def test_svg_decodes_to_public_url(self):
        svg = qr.render_svg("JGwYFNzK")

        result = decode(rasterize_segno_svg(svg))

        assert result.text == "https://memorial.example/m/JGwYFNzK"
        assert result.ec_level == "H"

    def test_svg_is_scalable(self):
        root = ET.fromstring(qr.render_svg("JGwYFNzK"))

        assert "viewBox" in root.attrib
        assert "width" not in root.attrib and "height" not in root.attrib

    def test_quiet_zone_present(self):
        image = Image.open(io.BytesIO(qr.render_png("JGwYFNzK"))).convert("L")
        border = qr.QUIET_ZONE * qr.PNG_SCALE

        assert image.crop((0, 0, image.width, border)).getextrema() == (255, 255)
        assert image.crop((0, 0, border, image.height)).getextrema() == (255, 255)


@pytest.mark.django_db
class TestEndpoint:
    @pytest.fixture
    def user(self):
        return UserFactory()

    @pytest.fixture
    def client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def url(self, memorial, fmt=None):
        suffix = f"?format={fmt}" if fmt else ""
        return f"/api/v1/memorials/{memorial.id}/qr/{suffix}"

    def test_svg_by_default(self, client, user):
        memorial = MemorialFactory(owner=user)

        response = client.get(self.url(memorial))

        assert response.status_code == 200
        assert response["Content-Type"] == "image/svg+xml"
        assert f"memorial-{memorial.short_code}-qr.svg" in response["Content-Disposition"]
        result = decode(rasterize_segno_svg(response.content))
        assert result.text == f"https://memorial.example/m/{memorial.short_code}"

    def test_png(self, client, user):
        memorial = MemorialFactory(owner=user)

        response = client.get(self.url(memorial, "png"))

        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        result = decode(Image.open(io.BytesIO(response.content)))
        assert result.text == f"https://memorial.example/m/{memorial.short_code}"

    def test_available_for_draft(self, client, user):
        memorial = MemorialFactory(owner=user)

        assert client.get(self.url(memorial, "png")).status_code == 200

    def test_unknown_format(self, client, user):
        response = client.get(self.url(MemorialFactory(owner=user), "gif"))

        assert response.status_code == 400

    def test_foreign_memorial(self, client):
        assert client.get(self.url(MemorialFactory(), "svg")).status_code == 404

    def test_anonymous(self):
        assert APIClient().get(self.url(MemorialFactory())).status_code == 401
