from django.core.management.base import BaseCommand

from apps.themes.seed import seed_themes


class Command(BaseCommand):
    help = "Создаёт стартовый каталог тем из apps/themes/fixtures/themes.json (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Привести уже существующие темы к фикстурам (перезапишет правки из админки).",
        )

    def handle(self, *args, update: bool, **options):
        for result in seed_themes(update=update):
            self.stdout.write(f"{result.key}: {result.status}")
