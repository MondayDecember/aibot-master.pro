import re

from utils.texts import _TEXTS, t


def test_translations_have_same_keys():
    assert set(_TEXTS["en"]) == set(_TEXTS["ru"]), set(_TEXTS["en"]) ^ set(_TEXTS["ru"])


def test_translations_have_same_placeholders():
    for key in _TEXTS["en"]:
        ph_en = set(re.findall(r"\{(\w+)\}", _TEXTS["en"][key]))
        ph_ru = set(re.findall(r"\{(\w+)\}", _TEXTS["ru"][key]))
        assert ph_en == ph_ru, (key, ph_en, ph_ru)


def test_t_formats_arguments():
    assert "5" in t("rate_limited", limit=5)


def test_t_survives_braces_in_values():
    # str.format must not re-interpret braces inside substituted values
    assert "{x}" in t("heard", text="code {x}")
