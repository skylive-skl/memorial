from modeltranslation.translator import TranslationOptions, register

from apps.themes.models import Theme


@register(Theme)
class ThemeTranslationOptions(TranslationOptions):
    fields = ("name",)
    required_languages = ("ru",)
