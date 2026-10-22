import factory

from apps.accounts.models import User

PASSWORD = "Str0ng-pass-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.django.Password(PASSWORD)
