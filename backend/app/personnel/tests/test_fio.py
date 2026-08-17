"""Tests for Russian ФИО declension.

Kazakh names in the Kazakh templates stay nominative, so the only declension we
assert is Russian. Kazakh -ұлы/-қызы surnames must pass through unchanged.
"""
from app.personnel.helpers.fio import decline_fio, fio_full, fio_short


def test_genitive_male():
    assert fio_full("Климов", "Василий", "Александрович", case="genitive", gender="male") == \
        "Климова Василия Александровича"


def test_dative_male():
    assert fio_full("Климов", "Василий", "Александрович", case="dative", gender="male") == \
        "Климову Василию Александровичу"


def test_accusative_male():
    assert fio_full("Климов", "Василий", "Александрович", case="accusative", gender="male") == \
        "Климова Василия Александровича"


def test_genitive_female():
    assert fio_full("Климова", "Мария", "Ивановна", case="genitive", gender="female") == \
        "Климовой Марии Ивановны"


def test_nominative_returns_input():
    assert fio_full("Климов", "Василий", "Александрович", case="nominative", gender="male") == \
        "Климов Василий Александрович"


def test_kazakh_surname_indeclinable():
    parts = decline_fio("Нұрланұлы", "Асхат", "", case="genitive", gender="male")
    assert parts["last"] == "Нұрланұлы"  # surname must not be mangled by Russian rules


def test_kazakh_patronymic_indeclinable():
    # -ұлы в отчестве не склоняется ни в одном падеже, а русская фамилия — склоняется
    for case in ("genitive", "dative", "accusative"):
        parts = decline_fio("Оналбаев", "Дидар", "Жанатұлы", case=case, gender="male")
        assert parts["middle"] == "Жанатұлы", (case, parts["middle"])
    assert decline_fio("Оналбаев", "Дидар", "Жанатұлы", "genitive", "male")["last"] == "Оналбаева"


def test_short_form():
    assert fio_short("Климов", "Василий", "Александрович") == "Климов В.А."
    assert fio_short("Климов", "Василий") == "Климов В."
