import copy

import factory

from apps.themes.models import Theme, ThemeAsset

VALID_TOKENS = {
    "schemaVersion": 1,
    "layout": "classic",
    "layoutOptions": {"photoShape": "oval", "gallery": "grid"},
    "colors": {
        "background": "#F7F5F0",
        "surface": "#FFFFFF",
        "text": "#2B2B2B",
        "muted": "#7A7468",
        "accent": "#8C6D3F",
        "border": "rgba(0, 0, 0, 0.1)",
    },
    "fonts": {"heading": "Playfair Display", "body": "Inter"},
    "background": {"type": "color", "asset": None, "value": None, "overlay": None},
    "ornaments": {"top": None, "divider": None, "photoFrame": None},
    "radius": "12px",
}


def make_tokens(**overrides) -> dict:
    """Валидные tokens с перезаписью секций верхнего уровня."""
    tokens = copy.deepcopy(VALID_TOKENS)
    tokens.update(copy.deepcopy(overrides))
    return tokens


class ThemeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Theme

    key = factory.Sequence(lambda n: f"theme-{n}")
    name = factory.Sequence(lambda n: f"Тема {n}")
    category = Theme.Category.NEUTRAL
    tokens = factory.LazyFunction(make_tokens)


class ThemeAssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ThemeAsset

    theme = factory.SubFactory(ThemeFactory)
    key = factory.Sequence(lambda n: f"asset-{n}")
    kind = ThemeAsset.Kind.ORNAMENT
    file = factory.django.FileField(filename="ornament.svg", data=b"<svg/>")
