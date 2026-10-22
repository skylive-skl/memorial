import factory

from apps.accounts.tests.factories import UserFactory
from apps.memorials.models import Memorial
from apps.themes.tests.factories import ThemeFactory


class MemorialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Memorial

    owner = factory.SubFactory(UserFactory)
    first_name = "Иван"
    last_name = "Петров"
    theme = factory.SubFactory(ThemeFactory)
