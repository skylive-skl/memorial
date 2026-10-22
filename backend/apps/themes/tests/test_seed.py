from io import StringIO

import pytest
from django.core.management import call_command

from apps.themes.models import Theme, ThemeAsset
from apps.themes.schema import validate_asset_refs, validate_tokens
from apps.themes.seed import ASSETS_DIR, load_theme_fixtures, seed_themes

FIXTURES = load_theme_fixtures()


def snapshot() -> dict:
    """Всё, что не должно меняться при повторном запуске."""
    return {
        theme.key: (
            theme.version,
            theme.updated_at,
            theme.preview_image.name,
            sorted(theme.assets.values_list("id", "key", "kind", "file")),
        )
        for theme in Theme.objects.all()
    }


class TestFixtures:
    def test_catalog_shape(self):
        keys = [f["key"] for f in FIXTURES]
        assert len(keys) >= 6
        assert len(set(keys)) == len(keys)
        assert {f["tokens"]["layout"] for f in FIXTURES} == {"classic", "gallery"}
        assert len({f["category"] for f in FIXTURES}) >= 3

    @pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["key"])
    def test_fixture_is_valid(self, fixture):
        assets = {a["key"]: a["kind"] for a in fixture["assets"]}

        assert validate_tokens(fixture["tokens"]) == []
        assert validate_asset_refs(fixture["tokens"], assets) == []
        assert set(fixture["name"]) == {"ru", "uz", "en"}
        for asset in fixture["assets"]:
            assert (ASSETS_DIR / asset["file"]).is_file()


@pytest.mark.django_db
class TestSeedThemes:
    def test_creates_all_themes_with_assets_and_previews(self):
        out = StringIO()

        call_command("seed_themes", stdout=out)

        assert Theme.objects.count() == len(FIXTURES)
        assert out.getvalue().count(": created") == len(FIXTURES)
        for fixture in FIXTURES:
            theme = Theme.objects.get(key=fixture["key"])
            theme.full_clean()
            assert theme.version == 1
            assert theme.name_uz == fixture["name"]["uz"]
            assert theme.layout_key == fixture["tokens"]["layout"]
            assert theme.preview_image
            assert dict(theme.assets.values_list("key", "kind")) == {
                a["key"]: a["kind"] for a in fixture["assets"]
            }

    def test_second_run_changes_nothing(self):
        seed_themes()
        before = snapshot()

        results = seed_themes()

        assert {r.status for r in results} == {"skipped"}
        assert snapshot() == before

    def test_update_without_changes_reuploads_nothing(self):
        seed_themes()
        before = snapshot()

        results = seed_themes(update=True)

        assert {r.status for r in results} == {"unchanged"}
        assert snapshot() == before

    def test_admin_edits_are_kept_without_update(self):
        seed_themes()
        theme = Theme.objects.get(key="classic-ivory")
        theme.tokens["radius"] = "0"
        theme.save()

        seed_themes()

        theme.refresh_from_db()
        assert theme.tokens["radius"] == "0"

    def test_update_restores_fixture_and_bumps_version(self):
        seed_themes()
        theme = Theme.objects.get(key="classic-emerald")
        theme.tokens["radius"] = "0"
        theme.name_uz = "Boshqa"
        theme.save()
        ThemeAsset.objects.filter(theme=theme, key="divider").delete()
        theme.tokens["ornaments"]["divider"] = None
        theme.save()

        results = {r.key: r.status for r in seed_themes(update=True)}

        theme.refresh_from_db()
        assert results["classic-emerald"] == "updated"
        assert results["classic-ivory"] == "unchanged"
        assert theme.tokens["radius"] == "8px"
        assert theme.name_uz == "Zumrad"
        assert theme.assets.filter(key="divider").exists()
        assert theme.version == 4

    def test_update_removes_assets_not_in_fixture(self):
        seed_themes()
        theme = Theme.objects.get(key="gallery-graphite")
        ThemeAsset.objects.create(theme=theme, key="extra", kind="icon", file="x.svg")

        seed_themes(update=True)

        assert not theme.assets.exists()
