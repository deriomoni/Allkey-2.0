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


def test_gender_drives_declension_female():
    # Пол управляет склонением фамилии и имени; -қызы не склоняется
    assert fio_full("Оналбаева", "Дана", "Жанатқызы", "genitive", "female") == "Оналбаевой Даны Жанатқызы"
    assert fio_full("Оналбаева", "Дана", "Жанатқызы", "dative", "female") == "Оналбаевой Дане Жанатқызы"
    assert fio_full("Оналбаева", "Дана", "Жанатқызы", "accusative", "female") == "Оналбаеву Дану Жанатқызы"
    # тот же корень, мужской пол — другая форма фамилии/имени
    assert fio_full("Оналбаев", "Дидар", "Жанатұлы", "genitive", "male") == "Оналбаева Дидара Жанатұлы"


def test_kazakh_surname_without_russian_suffix_indeclinable():
    # «Оспан» (казахская фамилия без -ов/-ев) и «Айгүл» не склоняются ни в одном падеже
    for case in ("genitive", "dative", "accusative"):
        assert fio_full("Оспан", "Айгүл", "Ерланқызы", case, "female") == "Оспан Айгүл Ерланқызы"


def test_first_name_declension_rule():
    from app.personnel.helpers.fio import _decline_part
    expected_genitive = {
        # мужские, склоняются (правило)
        ("Нұрлан", "male"): "Нұрлана", ("Ержан", "male"): "Ержана",
        ("Тимур", "male"): "Тимура", ("Бекзат", "male"): "Бекзата",
        ("Ерболат", "male"): "Ерболата", ("Бауыржан", "male"): "Бауыржана",
        ("Санжар", "male"): "Санжара", ("Аслан", "male"): "Аслана",
        ("Абай", "male"): "Абая",            # -й
        ("Мұстафа", "male"): "Мұстафы",      # мужское на -а
        # женские на -а, склоняются
        ("Мадина", "female"): "Мадины", ("Динара", "female"): "Динары",
        # женские на согласную / -е — не склоняются
        ("Әсем", "female"): "Әсем", ("Жанар", "female"): "Жанар",
        ("Аружан", "female"): "Аружан", ("Асель", "female"): "Асель",
        ("Сауле", "female"): "Сауле", ("Гүлнар", "female"): "Гүлнар",
        ("Ботагөз", "female"): "Ботагөз", ("Жұлдыз", "female"): "Жұлдыз",
        # русские через правило
        ("Василий", "male"): "Василия", ("Мария", "female"): "Марии",
    }
    for (name, gender), gen in expected_genitive.items():
        assert _decline_part(name, "first", "genitive", gender) == gen, name


def test_first_name_exceptions_override_rule():
    from app.personnel.helpers.fio import _decline_part
    # русские с беглой гласной/ё — из name_exceptions, правило их берёт неверно
    assert _decline_part("Пётр", "first", "genitive", "male") == "Петра"
    assert _decline_part("Павел", "first", "dative", "male") == "Павлу"


def test_hyphenated_first_name():
    from app.personnel.helpers.fio import _decline_part
    assert _decline_part("Нұрлан-Ержан", "first", "genitive", "male") == "Нұрлана-Ержана"


def test_consonant_surname_gender_sensitive():
    from app.personnel.helpers.fio import _decline_part
    # мужская фамилия на согласную склоняется, женская — нет
    assert _decline_part("Ким", "last", "genitive", "male") == "Кима"
    assert _decline_part("Ким", "last", "genitive", "female") == "Ким"
    assert _decline_part("Цой", "last", "genitive", "male") == "Цоя"
    assert _decline_part("Цой", "last", "genitive", "female") == "Цой"
    # -о/-е русские фамилии не склоняются у обоих
    assert _decline_part("Шевченко", "last", "genitive", "male") == "Шевченко"
    assert _decline_part("Шевченко", "last", "genitive", "female") == "Шевченко"


def test_short_form():
    assert fio_short("Климов", "Василий", "Александрович") == "Климов В.А."
    assert fio_short("Климов", "Василий") == "Климов В."
