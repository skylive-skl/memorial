import pytest

from apps.themes.schema import validate_asset_refs, validate_tokens
from apps.themes.tests.factories import VALID_TOKENS, make_tokens


def errors_for(**overrides) -> list[str]:
    return validate_tokens(make_tokens(**overrides))


def test_valid_tokens():
    assert validate_tokens(VALID_TOKENS) == []


def test_gallery_layout_with_its_options():
    tokens = make_tokens(
        layout="gallery", layoutOptions={"galleryStyle": "slider", "descriptionPosition": "side"}
    )

    assert validate_tokens(tokens) == []


def test_layout_options_are_optional():
    tokens = make_tokens()
    del tokens["layoutOptions"]

    assert validate_tokens(tokens) == []


def test_not_an_object():
    assert validate_tokens(["nope"])


@pytest.mark.parametrize(
    ("overrides", "expected_path"),
    [
        ({"schemaVersion": 2}, "tokens.schemaVersion"),
        ({"layout": "unknown"}, "tokens.layout"),
        ({"radius": "12px; color: red"}, "tokens.radius"),
        ({"fonts": {"heading": "Comic Sans MS", "body": "Inter"}}, "tokens.fonts.heading"),
        ({"fonts": {"heading": "Roboto", "body": "Inter"}}, "tokens.fonts.heading"),
        ({"unexpected": True}, "tokens"),
    ],
)
def test_invalid_top_level(overrides, expected_path):
    errors = errors_for(**overrides)

    assert errors
    assert errors[0].startswith(f"{expected_path}:")


def test_missing_required_color():
    colors = dict(VALID_TOKENS["colors"])
    del colors["accent"]

    errors = errors_for(colors=colors)

    assert any("'accent' is a required property" in e for e in errors)


@pytest.mark.parametrize("value", ["red", "#12345", "#GGGGGG", "rgba(0,0,0)x", "url(x)"])
def test_invalid_color(value):
    errors = errors_for(colors={**VALID_TOKENS["colors"], "text": value})

    assert errors[0].startswith("tokens.colors.text:")


@pytest.mark.parametrize(
    "value", ["#fff", "#FFFFFF", "#ffffff80", "rgb(1, 2, 3)", "rgba(1,2,3,.5)"]
)
def test_valid_colors(value):
    assert errors_for(colors={**VALID_TOKENS["colors"], "text": value}) == []


def test_layout_options_validated_by_layout_schema():
    errors = errors_for(layoutOptions={"photoShape": "triangle"})

    assert errors[0].startswith("tokens.layoutOptions.photoShape:")


def test_layout_options_of_other_layout_rejected():
    errors = errors_for(layoutOptions={"galleryStyle": "slider"})

    assert errors[0].startswith("tokens.layoutOptions:")


class TestBackground:
    def test_image_requires_asset(self):
        errors = errors_for(background={"type": "image", "asset": None})

        assert errors[0].startswith("tokens.background.asset:")

    def test_image_with_asset(self):
        assert errors_for(background={"type": "image", "asset": "bg-main"}) == []

    def test_gradient(self):
        value = "linear-gradient(180deg, #fff 0%, rgba(0,0,0,0.2) 100%)"

        assert errors_for(background={"type": "gradient", "value": value}) == []

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "red",
            "linear-gradient(#fff, #000); background: url(https://evil)",
            "linear-gradient(#fff, #000)} body {display:none",
            'linear-gradient("#fff", #000)',
        ],
    )
    def test_invalid_or_unsafe_gradient(self, value):
        errors = errors_for(background={"type": "gradient", "value": value})

        assert errors[0].startswith("tokens.background.value:")

    def test_color_value_must_be_color(self):
        errors = errors_for(background={"type": "color", "value": "nope"})

        assert errors[0].startswith("tokens.background.value:")

    def test_unknown_type(self):
        errors = errors_for(background={"type": "video"})

        assert errors[0].startswith("tokens.background.type:")


class TestAssetRefs:
    def test_existing_refs_of_right_kind(self):
        tokens = make_tokens(
            background={"type": "image", "asset": "bg"},
            ornaments={"top": "orn", "divider": "orn", "photoFrame": "frm"},
        )
        assets = {"bg": "background", "orn": "ornament", "frm": "frame"}

        assert validate_asset_refs(tokens, assets) == []

    def test_missing_asset(self):
        tokens = make_tokens(ornaments={"divider": "divider-1"})

        assert validate_asset_refs(tokens, {}) == [
            "tokens.ornaments.divider: asset 'divider-1' does not exist in this theme"
        ]

    def test_wrong_kind(self):
        tokens = make_tokens(background={"type": "image", "asset": "orn"})

        errors = validate_asset_refs(tokens, {"orn": "ornament"})

        assert errors == [
            "tokens.background.asset: asset 'orn' has kind 'ornament', expected 'background'"
        ]
